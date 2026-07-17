"""项目模型：项目 → 病人 → 阶段。

一个项目包含独立的 OCR/LLM/预处理配置、抽取模板和提示词工程。
项目下管理多个病人实例，每个病人有独立的工作目录。
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .patient import Patient, PatientStore, IMAGE_EXTS, STAGE_ORDER


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# 项目侧默认：空覆盖 = 继承全局（新项目）
DEFAULT_OCR_CONFIG: Dict[str, Any] = {}
DEFAULT_LLM_CONFIG: Dict[str, Any] = {}

DEFAULT_PREPROCESS_CONFIG = {
    "preset": "paper_photo",
    "ops": None,
    "mask_regions": [],
    "roi_regions": [],
    "collect_metrics": True,
}


@dataclass
class Project:
    """项目实例。"""
    id: str
    name: str
    source_type: str = "image"  # "image" | "excel" | "text"
    workspace: str = ""

    # OCR/LLM：默认继承全局；use_global=False 时 ocr_config/llm_config 为覆盖
    ocr_use_global: bool = True
    llm_use_global: bool = True
    ocr_config: Dict[str, Any] = field(default_factory=dict)
    llm_config: Dict[str, Any] = field(default_factory=dict)
    preprocess_config: Dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_PREPROCESS_CONFIG))
    slice_regions: List[Dict] = field(default_factory=list)
    make_docx: bool = False

    # 批量加速：默认跟全局；覆盖时 max_parallel_patients 为 1–4
    execution_use_global: bool = True
    max_parallel_patients: Optional[int] = None

    # 模板
    extraction_template: str = ""  # Excel/JSON 路径
    output_excel: str = ""

    # 提示词工程
    prompt_global: str = ""       # 项目级全局提示词
    prompt_fields: Dict = field(default_factory=dict)  # 字段级规则
    prompt_engineered_md: str = ""  # 最终渲染的 .md 路径
    prompt_template_path: str = ""  # Jinja 模板路径(可选覆盖)

    # 密钥引用(与 ConfigManager 兼容)
    ocr_token_ref: str = ""
    llm_api_key_ref: str = ""

    # 元数据
    created_at: str = ""
    updated_at: str = ""

    # 运行时
    _patient_store: Optional[PatientStore] = field(default=None, repr=False)

    def __post_init__(self):
        if not self.created_at:
            self.created_at = _now()
        if not self.updated_at:
            self.updated_at = _now()
        if not self.workspace:
            self.workspace = str(Path(self._default_workspace_root()) / self.id)

    def _default_workspace_root(self) -> Path:
        from . import WORKSPACE
        return WORKSPACE

    @property
    def patients_dir(self) -> Path:
        return Path(self.workspace) / "patients"

    @property
    def state_file(self) -> Path:
        return Path(self.workspace) / "project.json"

    @property
    def prompt_dir(self) -> Path:
        return Path(self.workspace) / "prompt"

    @property
    def patient_store(self) -> PatientStore:
        if self._patient_store is None:
            self.patients_dir.mkdir(parents=True, exist_ok=True)
            self._patient_store = PatientStore(self.patients_dir)
            self._patient_store.load()
        return self._patient_store

    # ---- 持久化 ----
    def to_json(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "source_type": self.source_type,
            "workspace": self.workspace,
            "ocr_use_global": self.ocr_use_global,
            "llm_use_global": self.llm_use_global,
            "ocr_config": self.ocr_config,
            "llm_config": self.llm_config,
            "preprocess_config": self.preprocess_config,
            "slice_regions": self.slice_regions,
            "make_docx": self.make_docx,
            "execution_use_global": self.execution_use_global,
            "max_parallel_patients": self.max_parallel_patients,
            "extraction_template": self.extraction_template,
            "output_excel": self.output_excel,
            "prompt_global": self.prompt_global,
            "prompt_fields": self.prompt_fields,
            "prompt_engineered_md": self.prompt_engineered_md,
            "prompt_template_path": self.prompt_template_path,
            "ocr_token_ref": self.ocr_token_ref,
            "llm_api_key_ref": self.llm_api_key_ref,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @staticmethod
    def from_json(data: dict) -> "Project":
        ocr_cfg = data.get("ocr_config") or {}
        llm_cfg = data.get("llm_config") or {}
        # 旧数据无 use_global 字段：有实质配置则视为覆盖，保持行为
        if "ocr_use_global" in data:
            ocr_use_global = bool(data.get("ocr_use_global"))
        else:
            ocr_use_global = not bool(ocr_cfg)
        if "llm_use_global" in data:
            llm_use_global = bool(data.get("llm_use_global"))
        else:
            llm_use_global = not bool(
                (llm_cfg.get("model") or "").strip()
                or (llm_cfg.get("base_url") or "").strip()
                or (llm_cfg.get("provider") and llm_cfg.get("provider") not in ("", "DeepSeek"))
            )

        p = Project(
            id=data["id"],
            name=data["name"],
            source_type=data.get("source_type", "image"),
            workspace=data.get("workspace", ""),
            ocr_use_global=ocr_use_global,
            llm_use_global=llm_use_global,
            ocr_config=ocr_cfg if isinstance(ocr_cfg, dict) else {},
            llm_config=llm_cfg if isinstance(llm_cfg, dict) else {},
            preprocess_config=data.get("preprocess_config", dict(DEFAULT_PREPROCESS_CONFIG)),
            slice_regions=data.get("slice_regions", []),
            make_docx=data.get("make_docx", False),
            execution_use_global=bool(data.get("execution_use_global", True)),
            max_parallel_patients=(
                int(data["max_parallel_patients"])
                if data.get("max_parallel_patients") is not None
                else None
            ),
            extraction_template=data.get("extraction_template", ""),
            output_excel=data.get("output_excel", ""),
            prompt_global=data.get("prompt_global", ""),
            prompt_fields=data.get("prompt_fields", {}),
            prompt_engineered_md=data.get("prompt_engineered_md", ""),
            prompt_template_path=data.get("prompt_template_path", ""),
            ocr_token_ref=data.get("ocr_token_ref", ""),
            llm_api_key_ref=data.get("llm_api_key_ref", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )
        if not p.workspace:
            p.workspace = str(Path(p._default_workspace_root()) / p.id)
        return p

    def save(self):
        self.updated_at = _now()
        Path(self.workspace).mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(
            json.dumps(self.to_json(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def to_summary(self) -> dict:
        """精简视图。"""
        ps = self.patient_store
        patients = ps.all()
        # 密钥可能存在全局 keyring（项目设置保存时写入），不只看 llm_api_key_ref
        llm_key_ok = bool(self.llm_api_key_ref)
        ocr_key_ok = bool(self.ocr_token_ref)
        if not llm_key_ok or not ocr_key_ok:
            try:
                from .state import config as global_config
                if not llm_key_ok:
                    llm_key_ok = bool(global_config.get_secret("extract_llm"))
                if not ocr_key_ok:
                    ocr_key_ok = bool(global_config.get_secret("ocr_api"))
            except Exception:
                pass
        return {
            "id": self.id,
            "name": self.name,
            "source_type": self.source_type,
            "patient_count": len(patients),
            "created_at": self.created_at,
            "has_template": bool(self.extraction_template),
            "has_prompt": bool(self.prompt_engineered_md),
            "ocr_token_configured": ocr_key_ok,
            "llm_api_key_configured": llm_key_ok,
            "llm_provider": (self.llm_config or {}).get("provider", ""),
            "llm_model": (self.llm_config or {}).get("model", ""),
        }

    def to_detail(self) -> dict:
        """完整视图。"""
        return {**self.to_json(), "patients": [p.to_summary() for p in self.patient_store.all()]}

    # ---- 病人管理 ----
    def import_image_folder(self, folder: str) -> List[Patient]:
        """从图片文件夹导入病人(与旧 PatientStore.import_parent 相同)。"""
        return self.patient_store.import_parent(folder)

    def import_text_files(self, folder: str) -> List[Patient]:
        """从文本文件文件夹导入(MD/DOCX/TXT 每个文件=1病人)。"""
        TEXT_EXTS = {".md", ".txt", ".docx"}
        folder_path = Path(folder)
        added: List[Patient] = []
        if not folder_path.is_dir():
            return added
        for f in sorted(folder_path.iterdir()):
            if f.is_file() and f.suffix.lower() in TEXT_EXTS:
                p = self.patient_store.add_folder(str(f.parent))
                if p:
                    # 覆盖病人名称为文件名
                    p.name = f.stem
                    # 读取文本内容作为 merged_text
                    if f.suffix.lower() in (".md", ".txt"):
                        text = f.read_text(encoding="utf-8")
                        p.merged_md.write_text(text, encoding="utf-8")
                        p.stages["merge"].mark_done()
                        p.stages["merge"].data["char_count"] = len(text)
                        p.stages["merge"].data["merged_path"] = "merged.md"
                    p.stages["source"].data["data_source"] = "text"
                    p.stages["source"].data["source_file"] = str(f)
                    p.save()
                    added.append(p)
        return added

    def import_excel_rows(self, excel_path: str, text_columns: str = "") -> List[Patient]:
        """从 Excel 拆分:每行=1病人,指定列拼接为病历文本。"""
        import openpyxl

        wb = openpyxl.load_workbook(excel_path, read_only=True, data_only=True)
        ws = wb.active

        rows = list(ws.iter_rows(values_only=True))
        if len(rows) < 2:
            wb.close()
            return []

        # 第一行是表头
        headers = [str(c or "").strip() for c in rows[0]]
        
        # 确定哪些列用于拼接病历文本
        text_cols: List[int] = []
        if text_columns.strip():
            for col_name in text_columns.split(","):
                col_name = col_name.strip()
                if col_name in headers:
                    text_cols.append(headers.index(col_name))
        if not text_cols:
            # 默认使用所有列(除了明显的元数据列)
            skip = {"姓名", "名称", "name", "id", "编号", "序号"}
            text_cols = [i for i, h in enumerate(headers) if h.lower() not in skip]
        if not text_cols:
            text_cols = list(range(len(headers)))

        added: List[Patient] = []
        for row_idx, row in enumerate(rows[1:], start=2):
            if not any(cell is not None for cell in row):
                continue

            # 病人名称:优先用"姓名"列,否则用行号
            name = ""
            if "姓名" in headers:
                name_idx = headers.index("姓名")
                name = str(row[name_idx] or "").strip()
            if not name:
                name = f"病人{row_idx - 1}"

            # 拼接病历文本
            parts = []
            for col_idx in text_cols:
                if col_idx < len(row) and row[col_idx] is not None:
                    val = str(row[col_idx]).strip()
                    if val:
                        header = headers[col_idx]
                        parts.append(f"{header}: {val}")
            text = "\n".join(parts)

            if not text.strip():
                continue

            # 创建病人
            pid = uuid.uuid4().hex[:12]
            patient = Patient(
                id=pid,
                name=name,
                source_dir=excel_path,
                work_dir=str(self.patients_dir / pid),
            )
            patient.stages["source"].mark_done()
            patient.stages["source"].data["data_source"] = "excel"
            patient.stages["source"].data["source_file"] = excel_path
            patient.stages["source"].data["excel_row"] = row_idx
            patient.save()

            # 直接写入 merged.md(跳过 OCR)
            patient.merged_md.write_text(text, encoding="utf-8")
            patient.stages["merge"].mark_done()
            patient.stages["merge"].data["char_count"] = len(text)
            patient.stages["merge"].data["merged_path"] = "merged.md"

            self.patient_store.patients[pid] = patient
            self.patient_store._by_source[f"{excel_path}:{row_idx}"] = pid
            added.append(patient)

        wb.close()
        return added


class ProjectStore:
    """管理所有项目。"""

    def __init__(self, workspace: Path):
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.projects: Dict[str, Project] = {}
        self._load()

    def _load(self):
        """从 workspace 恢复所有项目。"""
        self.projects.clear()
        for state in sorted(self.workspace.glob("*/project.json")):
            try:
                data = json.loads(state.read_text(encoding="utf-8"))
                project = Project.from_json(data)
                self.projects[project.id] = project
            except (json.JSONDecodeError, OSError, KeyError):
                continue

    def create(self, name: str, source_type: str = "image") -> Project:
        """创建新项目。"""
        pid = uuid.uuid4().hex[:12]
        project = Project(id=pid, name=name, source_type=source_type)
        project.save()
        self.projects[pid] = project
        return project

    def get(self, project_id: str) -> Optional[Project]:
        return self.projects.get(project_id)

    def remove(self, project_id: str, delete_files: bool = True):
        p = self.projects.pop(project_id, None)
        if p and delete_files and p.workspace:
            import shutil
            work = Path(p.workspace)
            if work.is_dir():
                shutil.rmtree(work, ignore_errors=True)
        return p

    def rename(self, project_id: str, name: str) -> Optional[Project]:
        p = self.projects.get(project_id)
        if not p or not name.strip():
            return p
        p.name = name.strip()
        p.save()
        return p

    def all(self) -> List[Project]:
        return list(self.projects.values())

    def save_all(self):
        for p in self.projects.values():
            p.save()
