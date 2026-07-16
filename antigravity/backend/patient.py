"""病人实例模型：per-stage 状态 + state.json 持久化。

一个病人 = 一个源图片文件夹。每个病人在 workspace/<id>/ 下有独立工作目录，
存放各阶段中间产物与 state.json，支持关掉重开恢复。

与旧 patient.py 的区别：
- 每个阶段有独立的状态对象（status / started_at / finished_at / error / 产物信息）
- 支持 stale 标记（上游编辑后下游自动标记过期）
- 产物路径约定明确（preprocess/ slice/ ocr/ merged.md 等）
- state.json 实时持久化，每步执行后立即 save
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif"}

# 阶段顺序（与前端 StageNav 一致）
STAGE_ORDER: List[str] = [
    "source", "preprocess", "slice", "ocr", "merge", "extract", "review", "export"
]

STAGE_LABELS: Dict[str, str] = {
    "source": "源图",
    "preprocess": "预处理",
    "slice": "切片",
    "ocr": "OCR",
    "merge": "合并",
    "extract": "抽取",
    "review": "审核",
    "export": "导出",
}

STAGE_STATUS: tuple = ("pending", "running", "done", "error", "skipped", "stale")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _sanitize(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "_", name).strip() or "patient"


@dataclass
class StageState:
    """单个阶段的状态。"""
    status: str = "pending"
    started_at: str = ""
    finished_at: str = ""
    error: str = ""
    # 各阶段特有的额外信息（如 ocr 的 pages、preprocess 的 config_used 等）
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "data": self.data,
        }

    @staticmethod
    def from_dict(d: dict) -> "StageState":
        return StageState(
            status=d.get("status", "pending"),
            started_at=d.get("started_at", ""),
            finished_at=d.get("finished_at", ""),
            error=d.get("error", ""),
            data=d.get("data", {}),
        )

    def mark_running(self):
        self.status = "running"
        self.started_at = _now()
        self.error = ""

    def mark_done(self):
        self.status = "done"
        self.finished_at = _now()

    def mark_error(self, msg: str):
        self.status = "error"
        self.finished_at = _now()
        self.error = msg

    def mark_skipped(self, reason: str = ""):
        self.status = "skipped"
        self.finished_at = _now()
        self.data["skip_reason"] = reason

    def mark_stale(self):
        if self.status in ("done", "skipped"):
            self.status = "stale"


@dataclass
class Patient:
    """病人实例。"""
    id: str
    name: str
    source_dir: str
    work_dir: str
    created_at: str = ""
    updated_at: str = ""
    stages: Dict[str, StageState] = field(default_factory=dict)
    current_stage: str = "source"

    def __post_init__(self):
        if not self.created_at:
            self.created_at = _now()
        if not self.updated_at:
            self.updated_at = _now()
        for s in STAGE_ORDER:
            self.stages.setdefault(s, StageState())

    # ---- 产物路径约定 ----
    @property
    def preprocess_dir(self) -> Path:
        return Path(self.work_dir) / "preprocess"

    @property
    def slice_dir(self) -> Path:
        return Path(self.work_dir) / "slice"

    @property
    def ocr_dir(self) -> Path:
        return Path(self.work_dir) / "ocr"

    @property
    def merged_md(self) -> Path:
        return Path(self.work_dir) / "merged.md"

    @property
    def merged_docx(self) -> Path:
        return Path(self.work_dir) / "merged.docx"

    @property
    def extracted_json(self) -> Path:
        return Path(self.work_dir) / "extracted.json"

    @property
    def raw_response_path(self) -> Path:
        return Path(self.work_dir) / "extracted_raw_response.txt"

    @property
    def prompt_path(self) -> Path:
        p = Path(self.work_dir) / "_meta"
        return p / "llm_prompt.txt"

    @property
    def state_file(self) -> Path:
        return Path(self.work_dir) / "state.json"

    @property
    def log_file(self) -> Path:
        return Path(self.work_dir) / "log.jsonl"

    # ---- 源图 ----
    def source_images(self) -> List[Dict[str, Any]]:
        """返回源图片列表（含基本信息）。"""
        src = Path(self.source_dir)
        if not src.is_dir():
            return []
        result = []
        for p in sorted(src.iterdir()):
            if p.suffix.lower() in IMAGE_EXTS and p.is_file():
                result.append({
                    "name": p.name,
                    "path": str(p),
                    "size": p.stat().st_size,
                })
        return result

    def has_images(self) -> bool:
        return len(self.source_images()) > 0

    # ---- OCR 页列表 ----
    def ocr_pages(self) -> List[Dict[str, Any]]:
        """读取 OCR 目录下的逐页 md（附输入图元数据，便于前端缩略图）。"""
        if not self.ocr_dir.is_dir():
            return []
        meta_map = (self.stages.get("ocr") and self.stages["ocr"].data.get("page_meta")) or {}
        pages = []
        for md in sorted(self.ocr_dir.rglob("*.md")):
            if "merged" in md.name:
                continue
            try:
                text = md.read_text(encoding="utf-8")
            except OSError:
                text = ""
            stem = md.stem
            base_key = stem.rsplit("_", 1)[0] if "_" in stem and stem.rsplit("_", 1)[-1].isdigit() else stem
            meta = meta_map.get(stem) or meta_map.get(base_key) or {}
            layout_path = self.ocr_dir / f"{stem}.layout.json"
            if not layout_path.is_file():
                layout_path = self.ocr_dir / f"{base_key}_0.layout.json"
            row = {
                "page": stem,
                "text": text,
                "char_count": len(text),
                "md_path": str(md.relative_to(self.work_dir)),
                "has_layout": layout_path.is_file(),
            }
            if meta:
                row.update({
                    "source_stage": meta.get("source_stage"),
                    "source_relative": meta.get("source_relative"),
                    "source_image": meta.get("source_image"),
                    "parent_page": meta.get("parent_page"),
                    "region_name": meta.get("region_name"),
                    "display_label": meta.get("display_label"),
                    "input_mode": meta.get("input_mode"),
                    "image_source": meta.get("image_source") or meta.get("source_stage"),
                    "slice_base_stage": meta.get("slice_base_stage") or "",
                })
            pages.append(row)
        return pages

    # ---- 合并文本 ----
    def get_merged_text(self) -> Optional[str]:
        if self.merged_md.exists():
            try:
                return self.merged_md.read_text(encoding="utf-8")
            except OSError:
                pass
        return None

    # ---- 抽取结果 ----
    def get_extracted_fields(self) -> Optional[Dict]:
        if self.extracted_json.exists():
            try:
                return json.loads(self.extracted_json.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return None

    # ---- 中间产物列表 ----
    def artifact_paths(self) -> List[str]:
        base = Path(self.work_dir)
        if not base.is_dir():
            return []
        return sorted(
            str(p.relative_to(base))
            for p in base.rglob("*")
            if p.is_file() and p.name != "state.json" and p.name != "log.jsonl"
        )

    # ---- 上游查找（OCR 时按 切片→预处理→源图 顺序找图） ----
    def best_image_dir(self) -> Path:
        """兼容旧接口：优先返回切片目录，否则预处理/源图。

        新逻辑请用 ``ocr_inputs.resolve_ocr_inputs``，尊重 input_mode。
        """
        from .ocr_inputs import resolve_mode, full_page_dir, has_valid_slices
        if resolve_mode(self) == "slices" and has_valid_slices(self):
            return self.slice_dir
        return full_page_dir(self)

    # ---- 状态标记 ----
    def mark_downstream_stale(self, stage: str):
        """某阶段被编辑后，下游所有阶段标记为 stale。"""
        idx = STAGE_ORDER.index(stage) if stage in STAGE_ORDER else 0
        for downstream in STAGE_ORDER[idx + 1:]:
            self.stages[downstream].mark_stale()

    def overall_status(self) -> str:
        """汇总状态（给侧边栏卡片用）。"""
        statuses = [self.stages[s].status for s in STAGE_ORDER]
        if any(v == "running" for v in statuses):
            return "running"
        if any(v == "error" for v in statuses):
            return "error"
        if any(v == "stale" for v in statuses):
            return "stale"
        extract_done = self.stages["extract"].status == "done"
        review_status = self.stages["review"].status
        if extract_done and review_status == "pending":
            return "review_pending"
        if all(v in ("done", "skipped") for v in statuses):
            return "done"
        return "pending"

    def current_active_stage(self) -> str:
        """第一个非 done/skipped 的阶段。"""
        for s in STAGE_ORDER:
            st = self.stages[s].status
            if st not in ("done", "skipped"):
                return s
        return "export"

    def stage_progress(self, stage: str) -> Optional[Dict[str, Any]]:
        """某阶段的进度信息（如 OCR 的 current/total）。"""
        return self.stages[stage].data.get("progress")

    # ---- 持久化 ----
    def to_json(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "source_dir": self.source_dir,
            "work_dir": self.work_dir,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "current_stage": self.current_stage,
            "stages": {s: st.to_dict() for s, st in self.stages.items()},
        }

    @staticmethod
    def from_json(data: dict) -> "Patient":
        p = Patient(
            id=data["id"],
            name=data["name"],
            source_dir=data["source_dir"],
            work_dir=data["work_dir"],
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            current_stage=data.get("current_stage", "source"),
        )
        stages_data = data.get("stages", {})
        for s in STAGE_ORDER:
            if s in stages_data:
                p.stages[s] = StageState.from_dict(stages_data[s])
        return p

    def save(self):
        """持久化到 state.json。"""
        self.updated_at = _now()
        Path(self.work_dir).mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(
            json.dumps(self.to_json(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def append_log(self, stage: str, level: str, message: str):
        """追加一条日志到 log.jsonl。"""
        entry = {
            "timestamp": _now(),
            "stage": stage,
            "level": level,
            "message": message,
        }
        try:
            with self.log_file.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            pass

    # ---- 视图 ----
    def to_summary(self) -> dict:
        """给 GET /patients 用的精简视图。"""
        return {
            "id": self.id,
            "name": self.name,
            "status": self.overall_status(),
            "current_stage": self.current_active_stage(),
            "stage_progress": self.stage_progress(self.current_active_stage()),
            "error": self.stages[self.current_active_stage()].error if self.overall_status() == "error" else "",
            "image_count": len(self.source_images()),
        }

    def to_detail(self) -> dict:
        """给 GET /patients/{id} 用的完整视图。"""
        return {
            "id": self.id,
            "name": self.name,
            "source_dir": self.source_dir,
            "work_dir": self.work_dir,
            "status": self.overall_status(),
            "current_stage": self.current_active_stage(),
            "stages": {s: st.to_dict() for s, st in self.stages.items()},
            "images": self.source_images(),
            "ocr_pages": self.ocr_pages(),
            "merged_text": self.get_merged_text(),
            "extracted_fields": self.get_extracted_fields(),
            "artifacts": self.artifact_paths(),
        }


class PatientStore:
    """管理一批病人实例：导入、持久化、恢复。"""

    def __init__(self, workspace: Path):
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.patients: Dict[str, Patient] = {}
        self._by_source: Dict[str, str] = {}

    def add_folder(self, folder: str) -> Optional[Patient]:
        """把单个文件夹录入为一个病人实例（已存在则返回现有实例）。"""
        src = Path(folder)
        if not src.is_dir():
            return None
        existing_id = self._by_source.get(str(src.resolve()))
        if existing_id:
            return self.patients.get(existing_id)
        pid = uuid.uuid4().hex[:12]
        patient = Patient(
            id=pid,
            name=src.name,
            source_dir=str(src),
            work_dir=str(self.workspace / pid),
        )
        # source 阶段自动完成
        patient.stages["source"].mark_done()
        patient.stages["source"].data["image_count"] = len(patient.source_images())
        patient.save()
        self.patients[pid] = patient
        self._by_source[str(src.resolve())] = pid
        return patient

    def import_parent(self, parent: str) -> List[Patient]:
        """扫描父目录，把每个含图片的子文件夹录入为病人实例。"""
        parent_path = Path(parent)
        added: List[Patient] = []
        if not parent_path.is_dir():
            return added
        subdirs = sorted([d for d in parent_path.iterdir() if d.is_dir()])
        candidates = subdirs or [parent_path]
        for d in candidates:
            has_img = any(p.suffix.lower() in IMAGE_EXTS for p in d.rglob("*"))
            if not has_img:
                continue
            p = self.add_folder(str(d))
            if p and p.id not in {a.id for a in added}:
                added.append(p)
        return added

    def remove(self, patient_id: str, delete_files: bool = True):
        p = self.patients.pop(patient_id, None)
        if p:
            self._by_source.pop(str(Path(p.source_dir).resolve()), None)
            if delete_files:
                import shutil
                work = Path(p.work_dir)
                if work.is_dir() and work.resolve() != Path(p.source_dir).resolve():
                    shutil.rmtree(work, ignore_errors=True)

    def rename(self, patient_id: str, name: str) -> Optional[Patient]:
        p = self.patients.get(patient_id)
        if not p or not name.strip():
            return p
        p.name = name.strip()
        p.save()
        return p

    def all(self) -> List[Patient]:
        return list(self.patients.values())

    def get(self, patient_id: str) -> Optional[Patient]:
        return self.patients.get(patient_id)

    def save_all(self):
        for p in self.patients.values():
            p.save()

    def load(self):
        """从 workspace 恢复上次会话；把卡在 running 的阶段标为 interrupted。"""
        self.patients.clear()
        self._by_source.clear()
        for state in sorted(self.workspace.glob("*/state.json")):
            try:
                data = json.loads(state.read_text(encoding="utf-8"))
                patient = Patient.from_json(data)
                dirty = False
                for key, ss in patient.stages.items():
                    if ss.status == "running":
                        ss.mark_error("上次运行被中断（程序关闭或崩溃）")
                        dirty = True
                if dirty:
                    patient.save()
                self.patients[patient.id] = patient
                self._by_source[str(Path(patient.source_dir).resolve())] = patient.id
            except (json.JSONDecodeError, OSError, KeyError):
                continue
