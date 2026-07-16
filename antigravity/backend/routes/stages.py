"""阶段执行 + 产物读写 API。

核心端点：
- POST /stages/{patient_id}/{stage}/run   — 执行单个阶段
- POST /stages/{patient_id}/{stage}/rerun — 重新执行（清除旧产物）
- POST /stages/batch/{stage}/run          — 批量执行
- POST /tasks/{task_id}/stop              — 停止任务
- GET  /stages/{patient_id}/{stage}       — 读取阶段状态 + 产物
- PUT  /stages/{patient_id}/ocr/page/{page_name}  — 编辑 OCR 文本
- PUT  /stages/{patient_id}/merge/text    — 编辑合并文本
- PUT  /stages/{patient_id}/extract/fields — 编辑抽取字段
"""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..state import config, find_patient
from ..stage_runner import StageRunner
from ..ws import manager
from ..patient import STAGE_ORDER, Patient, IMAGE_EXTS

router = APIRouter(prefix="/stages", tags=["stages"])

_executor = ThreadPoolExecutor(max_workers=2)
_runners: Dict[str, StageRunner] = {}  # task_id → runner
_task_map: Dict[str, str] = {}  # task_id → patient_id


def _build_settings_for_patient(patient: Patient, project=None) -> dict:
    """构造 StageRunner 需要的 settings：项目覆盖 > 全局默认。"""
    from ..config_resolve import runner_settings_for_patient
    return runner_settings_for_patient(patient, project, config)


def _make_callbacks(task_id: str, patient_id: str = ""):
    """创建 StageRunner 的回调函数。"""
    def on_progress(pid: str, stage: str, current: int, total: int, message: str):
        manager.emit_stage_progress(pid, stage, current, total, message)
        # 同步侧栏进度
        p, _ = find_patient(pid)
        if p and stage == "ocr":
            p.stages["ocr"].data["progress"] = {
                "current": current, "total": total, "message": message,
            }
            try:
                manager.emit_patient_update(p.to_summary())
            except Exception:
                pass

    def on_log(pid: str, stage: str, level: str, message: str):
        manager.emit_log(pid, stage, level, message)
        # 同时写入病人日志文件
        p, _ = find_patient(pid)
        if p:
            p.append_log(stage, level, message)

    def on_stage_done(pid: str, stage: str, status: str, message: str):
        manager.emit_stage_done(pid, stage, status, message)
        # 推送病人状态更新
        p, _ = find_patient(pid)
        if p:
            manager.emit_patient_update(p.to_summary())

    def on_ocr_page(pid: str, page: Optional[dict], page_name: str, error: Optional[str], current: int, total: int):
        if error:
            manager.emit_ocr_page_error(pid, page_name, error, current, total)
        elif page:
            manager.emit_ocr_page_done(pid, page, current, total)
        p, _ = find_patient(pid)
        if p:
            p.stages["ocr"].data["progress"] = {
                "current": current, "total": total,
                "message": f"{page_name} 完成" if not error else f"{page_name} 失败",
            }
            try:
                manager.emit_patient_update(p.to_summary())
            except Exception:
                pass

    return on_progress, on_log, on_stage_done, on_ocr_page


# ============ 执行 ============

class RunRequest(BaseModel):
    rerun: bool = False


@router.post("/{patient_id}/{stage}/run")
def run_stage(patient_id: str, stage: str, req: RunRequest = RunRequest()):
    """执行单个病人的单个阶段。"""
    if stage not in STAGE_ORDER:
        raise HTTPException(400, f"未知阶段：{stage}")
    p, project = find_patient(patient_id)
    if not p:
        raise HTTPException(404, "病人不存在")
    if stage == "source":
        return {"task_id": "", "message": "source 阶段无需执行"}
    if stage == "export":
        raise HTTPException(400, "导出请使用 /export/excel")

    task_id = uuid.uuid4().hex[:12]
    settings = _build_settings_for_patient(p, project)
    on_progress, on_log, on_stage_done, on_ocr_page = _make_callbacks(task_id, patient_id)
    runner = StageRunner(settings, on_progress, on_log, on_stage_done, on_ocr_page)
    _runners[task_id] = runner
    _task_map[task_id] = patient_id

    manager.emit_stage_started(patient_id, stage, task_id)

    def _run():
        try:
            runner.run_single(p, stage, rerun=req.rerun)
        finally:
            _runners.pop(task_id, None)
            _task_map.pop(task_id, None)
            manager.emit_task_done(task_id, {"patient_id": patient_id, "stage": stage})

    _executor.submit(_run)
    return {"task_id": task_id, "patient_id": patient_id, "stage": stage}


class BatchRunRequest(BaseModel):
    patient_ids: List[str]
    rerun: bool = False


@router.post("/batch/{stage}/run")
def run_batch(stage: str, req: BatchRunRequest):
    """批量执行同一阶段。"""
    if stage not in STAGE_ORDER:
        raise HTTPException(400, f"未知阶段：{stage}")
    if not req.patient_ids:
        raise HTTPException(400, "未指定病人")

    # 从所有项目查找病人
    found = []
    for pid in req.patient_ids:
        p, project = find_patient(pid)
        if p:
            found.append((p, project))
    if not found:
        raise HTTPException(404, "所选病人均不存在")

    patients = [p for p, _ in found]
    # 用第一个病人的项目配置
    first_project = found[0][1]

    task_id = uuid.uuid4().hex[:12]
    settings = _build_settings_for_patient(patients[0], first_project)
    on_progress, on_log, on_stage_done, on_ocr_page = _make_callbacks(task_id)
    runner = StageRunner(settings, on_progress, on_log, on_stage_done, on_ocr_page)
    _runners[task_id] = runner

    for pid in req.patient_ids:
        manager.emit_stage_started(pid, stage, task_id)

    def _run():
        try:
            runner.run_batch(patients, stage, rerun=req.rerun)
        finally:
            _runners.pop(task_id, None)
            done = sum(1 for p in patients if p.stages.get(stage) and p.stages[stage].status == "done")
            err = sum(1 for p in patients if p.stages.get(stage) and p.stages[stage].status == "error")
            manager.emit_task_done(task_id, {"done": done, "error": err})
            # 更新所有病人卡片
            for p in patients:
                manager.emit_patient_update(p.to_summary())

    _executor.submit(_run)
    return {"task_id": task_id, "patient_count": len(patients)}


@router.post("/tasks/{task_id}/stop")
def stop_task(task_id: str):
    """停止正在运行的任务。"""
    runner = _runners.get(task_id)
    if not runner:
        raise HTTPException(404, "任务不存在或已完成")
    runner.stop()
    return {"ok": True}


@router.get("/tasks/active")
def list_active_tasks():
    """当前内存中的运行任务，供前端重连后恢复进度条。"""
    items = []
    for tid, runner in list(_runners.items()):
        pid = _task_map.get(tid, "")
        items.append({
            "task_id": tid,
            "patient_id": pid,
            "stopped": runner.is_stopped,
        })
    return {"tasks": items}


# ============ 阶段状态读取 ============

@router.get("/{patient_id}/{stage}")
def get_stage_detail(patient_id: str, stage: str):
    """读取某阶段的完整状态 + 产物。"""
    p, _proj = find_patient(patient_id)
    if not p:
        raise HTTPException(404, "病人不存在")
    if stage not in p.stages:
        raise HTTPException(400, f"未知阶段：{stage}")

    ss = p.stages[stage]
    result = {
        "patient_id": patient_id,
        "stage": stage,
        "status": ss.status,
        "started_at": ss.started_at,
        "finished_at": ss.finished_at,
        "error": ss.error,
        "data": ss.data,
    }

    # 附加阶段特有的产物信息
    if stage == "source":
        result["images"] = p.source_images()
    elif stage == "ocr":
        result["pages"] = p.ocr_pages()
    elif stage == "merge":
        result["merged_text"] = p.get_merged_text()
        result["char_count"] = len(p.get_merged_text() or "")
    elif stage == "extract":
        result["fields"] = p.get_extracted_fields()
    elif stage == "review":
        result["fields"] = p.get_extracted_fields()

    return result


# ============ OCR 文本编辑 ============

class EditOcrPageRequest(BaseModel):
    text: str


@router.put("/{patient_id}/ocr/page/{page_name}")
def edit_ocr_page(patient_id: str, page_name: str, req: EditOcrPageRequest):
    """编辑某页 OCR 文本。"""
    p, _proj = find_patient(patient_id)
    if not p:
        raise HTTPException(404, "病人不存在")

    md_path = p.ocr_dir / f"{page_name}.md"
    if not md_path.exists():
        # 尝试带 _0 后缀
        md_path = p.ocr_dir / f"{page_name}_0.md"
    if not md_path.exists():
        raise HTTPException(404, f"OCR 页面不存在：{page_name}")

    md_path.write_text(req.text, encoding="utf-8")
    p.stages["ocr"].data["edited"] = True
    p.mark_downstream_stale("ocr")
    p.save()
    manager.emit_patient_update(p.to_summary())
    return {"ok": True}


# ============ 合并文本编辑 ============

class EditMergeTextRequest(BaseModel):
    text: str


@router.put("/{patient_id}/merge/text")
def edit_merge_text(patient_id: str, req: EditMergeTextRequest):
    """编辑合并文本。"""
    p, _proj = find_patient(patient_id)
    if not p:
        raise HTTPException(404, "病人不存在")

    p.merged_md.write_text(req.text, encoding="utf-8")
    p.stages["merge"].data["char_count"] = len(req.text)
    p.stages["merge"].data["edited"] = True
    p.mark_downstream_stale("merge")
    p.save()
    manager.emit_patient_update(p.to_summary())
    return {"ok": True}


# ============ 抽取字段编辑 ============

class EditFieldsRequest(BaseModel):
    fields: Dict[str, Any]


@router.put("/{patient_id}/extract/fields")
def edit_extract_fields(patient_id: str, req: EditFieldsRequest):
    """编辑抽取字段值。"""
    p, _proj = find_patient(patient_id)
    if not p:
        raise HTTPException(404, "病人不存在")

    existing = p.get_extracted_fields()
    if not existing:
        raise HTTPException(400, "尚未抽取，无法编辑")

    fields = existing.get("fields", {})
    for k, v in req.fields.items():
        if k in fields:
            if not isinstance(fields[k], dict):
                fields[k] = {"value": v, "original_value": fields[k], "edited": True}
            else:
                fields[k]["value"] = v
                fields[k]["edited"] = True
        else:
            fields[k] = {"value": v, "original_value": None, "edited": True}

    existing["fields"] = fields
    p.extracted_json.write_text(
        __import__("json").dumps(existing, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    p.stages["extract"].data["edited"] = True
    p.save()
    return {"ok": True}


# ============ 单页重 OCR ============

@router.post("/{patient_id}/ocr/page/{page_name}/rerun")
def rerun_ocr_page(patient_id: str, page_name: str):
    """重新 OCR 单页（按当前 OCR 输入解析：切片/整页）。"""
    from ..ocr_inputs import build_ocr_page_meta, find_input_for_page

    p, project = find_patient(patient_id)
    if not p:
        raise HTTPException(404, "病人不存在")

    item = find_input_for_page(p, page_name)
    if not item:
        raise HTTPException(404, f"找不到对应的输入图片：{page_name}")

    file_path = item["path"]
    settings = _build_settings_for_patient(p, project)
    token = settings.get("ocr_token") or config.get_secret("ocr_api")
    if not token:
        raise HTTPException(400, "OCR Token 未配置")

    task_id = uuid.uuid4().hex[:12]
    _task_map[task_id] = patient_id
    manager.emit_stage_started(patient_id, "ocr", task_id)
    page_key = item["page_key"]
    meta = build_ocr_page_meta(item)
    label = item.get("display_label") or file_path.name

    def _run():
        from antigravity.engine.ocr_client import AsyncOCRClient, save_layout_results
        try:
            manager.emit_stage_progress(patient_id, "ocr", 0, 1, f"重新 OCR {label}")
            client = AsyncOCRClient(
                settings.get("ocr_url", ""),
                token,
                model=settings.get("ocr_model", ""),
                preset=settings.get("ocr_preset", "paper_photo"),
                custom_params=settings.get("ocr_custom_params", {}),
                user_presets=settings.get("ocr_user_presets", []),
                log_callback=lambda m: manager.emit_log(patient_id, "ocr", "info", m),
            )
            results = client.process_file(file_path)
            if results:
                for old in p.ocr_dir.glob(f"{page_key}*"):
                    old.unlink(missing_ok=True)
                img_meta = {
                    "stage": item.get("stage") or "source",
                    "relative": item.get("relative") or item.get("name") or "",
                    "name": item.get("name") or file_path.name,
                    "page_key": page_key,
                }
                save_layout_results(
                    results,
                    p.ocr_dir / page_key,
                    save_layout=True,
                    image_meta=img_meta,
                )
                md_path = p.ocr_dir / f"{page_key}_0.md"
                if not md_path.exists():
                    cands = sorted(p.ocr_dir.glob(f"{page_key}*.md"))
                    md_path = cands[0] if cands else md_path
                text = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
                meta["has_layout"] = True
                page = {
                    "page": md_path.stem if md_path.exists() else f"{page_key}_0",
                    "text": text,
                    "char_count": len(text),
                    "md_path": str(md_path.relative_to(p.work_dir)) if md_path.exists() else "",
                    **meta,
                }
                page_meta = dict(p.stages["ocr"].data.get("page_meta") or {})
                page_meta[page["page"]] = meta
                page_meta[page_key] = meta
                p.stages["ocr"].data["page_meta"] = page_meta
                manager.emit_ocr_page_done(patient_id, page, 1, 1)
                manager.emit_log(patient_id, "ocr", "info", f"✓ {label} 重新识别完成")
                p.stages["ocr"].data["edited"] = True
                p.mark_downstream_stale("ocr")
                p.save()
            manager.emit_stage_progress(patient_id, "ocr", 1, 1, "完成")
            manager.emit_stage_done(patient_id, "ocr", "done", "单页重新识别完成")
            manager.emit_patient_update(p.to_summary())
        except Exception as exc:
            manager.emit_log(patient_id, "ocr", "error", str(exc))
            manager.emit_ocr_page_error(patient_id, page_name, str(exc), 1, 1)
            manager.emit_stage_done(patient_id, "ocr", "error", str(exc))
        finally:
            _task_map.pop(task_id, None)
            manager.emit_task_done(task_id, {"patient_id": patient_id, "stage": "ocr"})

    _executor.submit(_run)
    return {"task_id": task_id, "message": f"正在重新 OCR {label}"}


# ============ LLM 原始响应 / Prompt ============

@router.get("/{patient_id}/extract/raw-response")
def get_raw_response(patient_id: str):
    """获取 LLM 原始响应。"""
    p, _proj = find_patient(patient_id)
    if not p:
        raise HTTPException(404, "病人不存在")
    if p.raw_response_path.exists():
        return {"text": p.raw_response_path.read_text(encoding="utf-8")}
    return {"text": ""}


@router.get("/{patient_id}/extract/prompt")
def get_prompt(patient_id: str):
    """获取抽取时使用的完整 prompt。"""
    p, _proj = find_patient(patient_id)
    if not p:
        raise HTTPException(404, "病人不存在")
    if p.prompt_path.exists():
        return {"text": p.prompt_path.read_text(encoding="utf-8")}
    return {"text": ""}


# ============ 搜索 OCR 文本 ============

class SearchRequest(BaseModel):
    query: str


@router.post("/{patient_id}/ocr/search")
def search_ocr(patient_id: str, req: SearchRequest):
    """在所有 OCR 页中搜索关键词。"""
    p, _proj = find_patient(patient_id)
    if not p:
        raise HTTPException(404, "病人不存在")
    if not req.query.strip():
        return {"results": []}

    results = []
    for page in p.ocr_pages():
        text = page.get("text", "")
        idx = text.lower().find(req.query.lower())
        if idx >= 0:
            start = max(0, idx - 30)
            end = min(len(text), idx + len(req.query) + 30)
            results.append({
                "page": page["page"],
                "snippet": text[start:end],
                "match_index": idx,
            })
    return {"results": results, "query": req.query}


# ============ 审核 ============

class ReviewRequest(BaseModel):
    reviewed_fields: Dict[str, Dict[str, Any]] = {}  # {field_name: {reviewed: bool, note: str}}
    all_reviewed: bool = False


@router.put("/{patient_id}/review")
def update_review(patient_id: str, req: ReviewRequest):
    """更新审核状态。"""
    p, _proj = find_patient(patient_id)
    if not p:
        raise HTTPException(404, "病人不存在")

    p.stages["review"].data["reviewed_fields"] = req.reviewed_fields
    if req.all_reviewed:
        p.stages["review"].mark_done()
    p.save()
    manager.emit_patient_update(p.to_summary())
    return {"ok": True}


# ============ 预处理参数 ============

class PreprocessConfigRequest(BaseModel):
    # 新流水线
    preset: Optional[str] = "paper_photo"
    ops: Optional[List[Dict[str, Any]]] = None
    roi_regions: Optional[List[Dict[str, Any]]] = None
    collect_metrics: Optional[bool] = True
    # 兼容旧字段
    contrast: Optional[float] = None
    sharpness: Optional[float] = None
    brightness: Optional[float] = None
    denoise: Optional[bool] = None
    binarize: Optional[bool] = None
    binarize_threshold: Optional[int] = None
    mask_regions: List[Dict[str, Any]] = []


@router.get("/preprocess/catalog")
def preprocess_catalog():
    """预处理预设与算子目录。"""
    from antigravity.engine.image_preprocess import describe_catalog
    return describe_catalog()


@router.get("/{patient_id}/preprocess/config")
def get_preprocess_config(patient_id: str):
    """获取预处理配置（场景预设 + 算子 + 遮罩 + 最近指标）。"""
    p, project = find_patient(patient_id)
    if not p:
        raise HTTPException(404, "病人不存在")
    data = p.stages["preprocess"].data
    config_used = data.get("config_used") or (project.preprocess_config if project else {}) or {}
    if not isinstance(config_used, dict):
        config_used = {}
    mask_regions = data.get("mask_regions")
    if mask_regions is None:
        mask_regions = config_used.get("mask_regions") or []
    if not mask_regions and project:
        mask_regions = (project.preprocess_config or {}).get("mask_regions", [])
    return {
        "preset": config_used.get("preset") or "paper_photo",
        "ops": config_used.get("ops"),
        "mask_regions": mask_regions or [],
        "roi_regions": data.get("roi_regions") or config_used.get("roi_regions") or [],
        "collect_metrics": config_used.get("collect_metrics", True),
        "metrics_summary": data.get("metrics_summary") or [],
        "metrics_score": data.get("metrics_score") or {},
        # 兼容旧 UI 字段
        "contrast": config_used.get("contrast", 2.0),
        "sharpness": config_used.get("sharpness", 2.0),
        "brightness": config_used.get("brightness", 1.2),
        "denoise": config_used.get("denoise", False),
        "binarize": config_used.get("binarize", False),
        "binarize_threshold": config_used.get("binarize_threshold", 140),
    }


@router.put("/{patient_id}/preprocess/config")
def set_preprocess_config(patient_id: str, req: PreprocessConfigRequest):
    """保存预处理配置（不立即执行，下次 run 时生效）。"""
    p, _proj = find_patient(patient_id)
    if not p:
        raise HTTPException(404, "病人不存在")
    flat: Dict[str, Any] = {
        "preset": req.preset or "paper_photo",
        "ops": req.ops,
        "mask_regions": req.mask_regions or [],
        "roi_regions": req.roi_regions or [],
        "collect_metrics": True if req.collect_metrics is None else req.collect_metrics,
    }
    # 若仍传旧字段，保留以便 legacy 预设
    for k in ("contrast", "sharpness", "brightness", "denoise", "binarize", "binarize_threshold"):
        v = getattr(req, k, None)
        if v is not None:
            flat[k] = v
    p.stages["preprocess"].data["config_used"] = flat
    p.stages["preprocess"].data["mask_regions"] = flat["mask_regions"]
    p.stages["preprocess"].data["roi_regions"] = flat["roi_regions"]
    p.save()
    return {"ok": True}


@router.post("/{patient_id}/preprocess/preview")
def preview_preprocess(patient_id: str, body: Dict[str, Any] = None):
    """对单张源图试跑预处理并返回指标（不覆盖整批产物，写到 preprocess_preview/）。"""
    from antigravity.engine.image_preprocess import process_image_file
    body = body or {}
    p, _proj = find_patient(patient_id)
    if not p:
        raise HTTPException(404, "病人不存在")
    name = body.get("image_name") or ""
    src_files = list(Path(p.source_dir).rglob("*")) if Path(p.source_dir).is_dir() else []
    src_files = [f for f in src_files if f.is_file() and f.suffix.lower() in IMAGE_EXTS]
    if not src_files:
        raise HTTPException(400, "无源图")
    if name:
        match = next((f for f in src_files if f.name == name), None)
        fp = match or src_files[0]
    else:
        fp = src_files[0]
    preset = body.get("preset") or "paper_photo"
    ops = body.get("ops")
    out_dir = Path(p.work_dir) / "preprocess_preview"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / fp.name
    try:
        result = process_image_file(
            str(fp),
            str(out_path),
            preset=preset,
            ops=ops,
            mask_regions=body.get("mask_regions") or p.stages["preprocess"].data.get("mask_regions") or [],
            roi_regions=body.get("roi_regions") or [],
            collect_metrics=True,
        )
    except Exception as exc:
        raise HTTPException(400, str(exc))
    return {
        "image_name": fp.name,
        "preview_relative": fp.name,
        "ms": result.get("ms"),
        "metrics_before": result.get("metrics_before"),
        "metrics_after": result.get("metrics_after"),
        "compare": result.get("compare"),
        "trace": result.get("trace"),
        "preview_url_hint": f"/files/image/{patient_id}/preprocess_preview/{fp.name}",
    }


class PreprocessBenchRequest(BaseModel):
    image_names: Optional[List[str]] = None
    presets: Optional[List[str]] = None
    limit: Optional[int] = 6
    mask_regions: Optional[List[Dict[str, Any]]] = None


@router.post("/{patient_id}/preprocess/bench")
def bench_preprocess(patient_id: str, body: PreprocessBenchRequest = None):
    """多预设 A/B：对若干源图批量试跑，返回指标表（不覆盖正式预处理产物）。"""
    from antigravity.engine.image_preprocess import process_image_file
    from antigravity.engine.image_preprocess.presets import PREPROCESS_PRESETS, DEFAULT_PREPROCESS_PRESET

    body = body or PreprocessBenchRequest()
    p, _proj = find_patient(patient_id)
    if not p:
        raise HTTPException(404, "病人不存在")

    src_files = list(Path(p.source_dir).rglob("*")) if Path(p.source_dir).is_dir() else []
    src_files = [f for f in src_files if f.is_file() and f.suffix.lower() in IMAGE_EXTS]
    if not src_files:
        raise HTTPException(400, "无源图")

    names = body.image_names or []
    if names:
        chosen = [f for f in src_files if f.name in set(names)]
        if not chosen:
            chosen = src_files[: max(1, min(int(body.limit or 6), len(src_files)))]
    else:
        limit = max(1, min(int(body.limit or 6), 20))
        chosen = src_files[:limit]

    preset_keys = body.presets or [
        "skip", "legacy", "screenshot", "screen_photo", "paper_photo", "handwritten", "watermark_heavy",
    ]
    preset_keys = [k for k in preset_keys if k in PREPROCESS_PRESETS] or [DEFAULT_PREPROCESS_PRESET]
    mask = body.mask_regions or p.stages["preprocess"].data.get("mask_regions") or []

    out_root = Path(p.work_dir) / "preprocess_bench"
    out_root.mkdir(parents=True, exist_ok=True)

    rows: List[Dict[str, Any]] = []
    for fp in chosen:
        for preset in preset_keys:
            out_dir = out_root / preset
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / fp.name
            try:
                result = process_image_file(
                    str(fp),
                    str(out_path),
                    preset=preset,
                    ops=None,
                    mask_regions=mask,
                    collect_metrics=True,
                )
                cmp_ = result.get("compare") or {}
                rows.append({
                    "image": fp.name,
                    "preset": preset,
                    "ms": result.get("ms"),
                    "verdict": cmp_.get("verdict"),
                    "score": cmp_.get("score"),
                    "delta": cmp_.get("delta"),
                    "metrics_before": result.get("metrics_before"),
                    "metrics_after": result.get("metrics_after"),
                    "trace": result.get("trace"),
                    "ok": True,
                    "preview_relative": f"{preset}/{fp.name}",
                })
            except Exception as exc:
                rows.append({
                    "image": fp.name,
                    "preset": preset,
                    "ok": False,
                    "error": str(exc),
                })

    # 按图汇总：哪个预设 score 最高
    by_image: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        if not r.get("ok"):
            continue
        by_image.setdefault(r["image"], []).append(r)
    winners = {}
    for img, items in by_image.items():
        best = max(items, key=lambda x: (x.get("score") or -99, -(x.get("ms") or 1e9)))
        winners[img] = {"preset": best["preset"], "score": best.get("score"), "ms": best.get("ms")}

    return {
        "images": [f.name for f in chosen],
        "presets": preset_keys,
        "rows": rows,
        "winners": winners,
        "bench_dir": str(out_root),
    }


# ============ 预处理图片列表 ============

@router.get("/{patient_id}/preprocess/images")
def get_preprocess_images(patient_id: str):
    """获取预处理后的图片列表。"""
    p, _proj = find_patient(patient_id)
    if not p:
        raise HTTPException(404, "病人不存在")
    if not p.preprocess_dir.is_dir():
        return {"images": [], "has_preprocessed": False}
    from ..patient import IMAGE_EXTS
    images = []
    for f in sorted(p.preprocess_dir.rglob("*")):
        if f.suffix.lower() in IMAGE_EXTS and f.is_file():
            images.append({
                "name": f.name,
                "relative": str(f.relative_to(p.preprocess_dir)),
                "size": f.stat().st_size,
            })
    return {"images": images, "has_preprocessed": len(images) > 0}


# ============ 预处理版本备份 / 恢复 ============

@router.get("/{patient_id}/preprocess/versions")
def list_preprocess_versions(patient_id: str):
    """列出 preprocess_history 中的版本（最近 5 版）。"""
    from pathlib import Path
    p, _proj = find_patient(patient_id)
    if not p:
        raise HTTPException(404, "病人不存在")
    hist = Path(p.work_dir) / "preprocess_history"
    if not hist.is_dir():
        return {"versions": [], "current_backup": p.stages["preprocess"].data.get("last_backup", "")}
    versions = []
    for d in sorted(
        [x for x in hist.iterdir() if x.is_dir() and x.name.startswith("v")],
        key=lambda x: int(x.name[1:]) if x.name[1:].isdigit() else 0,
        reverse=True,
    ):
        count = sum(1 for f in d.rglob("*") if f.is_file())
        versions.append({
            "version": d.name,
            "file_count": count,
            "path": str(d),
        })
    return {
        "versions": versions,
        "current_backup": p.stages["preprocess"].data.get("last_backup", ""),
    }


class RestorePreprocessRequest(BaseModel):
    version: str  # e.g. "v2"


@router.post("/{patient_id}/preprocess/restore")
def restore_preprocess(patient_id: str, req: RestorePreprocessRequest):
    """从历史版本恢复 preprocess/（先备份当前再覆盖）。"""
    import shutil
    from pathlib import Path
    p, _proj = find_patient(patient_id)
    if not p:
        raise HTTPException(404, "病人不存在")
    hist = Path(p.work_dir) / "preprocess_history" / req.version
    if not hist.is_dir():
        raise HTTPException(404, f"版本不存在：{req.version}")
    # 先备份当前
    if p.preprocess_dir.is_dir() and any(p.preprocess_dir.rglob("*")):
        from ..stage_runner import StageRunner
        StageRunner({})._backup_preprocess(p)
    if p.preprocess_dir.exists():
        shutil.rmtree(p.preprocess_dir, ignore_errors=True)
    shutil.copytree(hist, p.preprocess_dir)
    p.stages["preprocess"].mark_done()
    count = sum(1 for f in p.preprocess_dir.rglob("*") if f.is_file())
    p.stages["preprocess"].data["output_count"] = count
    p.stages["preprocess"].data["restored_from"] = req.version
    p.save()
    manager.emit_patient_update(p.to_summary())
    return {"ok": True, "version": req.version, "file_count": count}


# ============ 切片区域 ============

class SliceRegionsRequest(BaseModel):
    regions: List[Dict[str, Any]]  # [{name, x1, y1, x2, y2}]


@router.get("/{patient_id}/slice/regions")
def get_slice_regions(patient_id: str):
    """获取切片区域配置。"""
    p, _proj = find_patient(patient_id)
    if not p:
        raise HTTPException(404, "病人不存在")
    regions = p.stages["slice"].data.get("regions", [])
    return {"regions": regions}


@router.put("/{patient_id}/slice/regions")
def set_slice_regions(patient_id: str, req: SliceRegionsRequest):
    """保存切片区域配置。"""
    p, _proj = find_patient(patient_id)
    if not p:
        raise HTTPException(404, "病人不存在")
    p.stages["slice"].data["regions"] = req.regions
    p.save()
    return {"ok": True}


# ============ 切片预览 ============

@router.get("/{patient_id}/slice/preview/{image_name:path}")
def get_slice_preview(patient_id: str, image_name: str):
    """获取某张图的切片结果列表。"""
    p, _proj = find_patient(patient_id)
    if not p:
        raise HTTPException(404, "病人不存在")
    stem = image_name.rsplit(".", 1)[0] if "." in image_name else image_name
    slice_subdir = p.slice_dir / stem
    if not slice_subdir.is_dir():
        return {"slices": [], "has_slices": False}
    from ..patient import IMAGE_EXTS
    slices = []
    for f in sorted(slice_subdir.iterdir()):
        if f.suffix.lower() in IMAGE_EXTS and f.is_file():
            slices.append({
                "name": f.name,
                "relative": str(f.relative_to(p.slice_dir)).replace("\\", "/"),
                "size": f.stat().st_size,
            })
    return {"slices": slices, "has_slices": len(slices) > 0}


@router.get("/{patient_id}/ocr/inputs")
def get_ocr_inputs(patient_id: str):
    """当前 OCR 将使用的输入清单（切片/整页 × 预处理/原图）。"""
    from ..ocr_inputs import resolve_ocr_inputs
    p, _proj = find_patient(patient_id)
    if not p:
        raise HTTPException(404, "病人不存在")
    plan = resolve_ocr_inputs(p)
    return {
        "requested_mode": plan["requested_mode"],
        "effective_mode": plan["effective_mode"],
        "image_source_requested": plan.get("image_source_requested", "auto"),
        "image_source_effective": plan.get("image_source_effective", "source"),
        "image_source_label": plan.get("image_source_label", ""),
        "structure_label": plan.get("structure_label", ""),
        "count": plan["count"],
        "message": plan["message"],
        "warning": plan["warning"],
        "error": plan.get("error") or "",
        "has_slices": plan["has_slices"],
        "has_preprocess": plan.get("has_preprocess", False),
        "has_source": plan.get("has_source", False),
        "preprocess_count": plan.get("preprocess_count", 0),
        "source_count": plan.get("source_count", 0),
        "slice_region_count": plan["slice_region_count"],
        "slice_status": plan["slice_status"],
        "slice_base_stage": plan.get("slice_base_stage") or "",
        "items": [
            {
                "name": it["name"],
                "relative": it["relative"],
                "stage": it["stage"],
                "page_key": it["page_key"],
                "parent_page": it.get("parent_page", ""),
                "region_name": it.get("region_name", ""),
                "display_label": it.get("display_label", ""),
                "image_source": it.get("image_source") or it.get("stage"),
                "slice_base_stage": it.get("slice_base_stage") or "",
            }
            for it in plan["items"]
        ],
    }


@router.get("/{patient_id}/ocr/pages/{page_name}/layout")
def get_ocr_page_layout(patient_id: str, page_name: str):
    """读取 OCR 页版面块（用于图上标定）。"""
    from antigravity.engine.ocr_layout import find_layout_path, load_layout_json
    p, _proj = find_patient(patient_id)
    if not p:
        raise HTTPException(404, "病人不存在")
    path = find_layout_path(p.ocr_dir, page_name)
    if not path:
        return {
            "ok": False,
            "has_layout": False,
            "page": page_name,
            "message": "无版面数据，请重新 OCR 以启用图上定位",
            "blocks": [],
            "image": {},
        }
    layout = load_layout_json(path)
    if not layout:
        raise HTTPException(500, "layout 文件损坏")
    # 补全 image 信息：优先 layout，其次 page_meta
    meta_map = p.stages["ocr"].data.get("page_meta") or {}
    meta = meta_map.get(page_name) or meta_map.get(page_name.replace("_0", "")) or {}
    image = dict(layout.get("image") or {})
    if not image.get("relative") and meta:
        image["stage"] = meta.get("source_stage") or image.get("stage") or "source"
        image["relative"] = meta.get("source_relative") or meta.get("source_image") or ""
        image["name"] = meta.get("source_image") or image.get("name") or ""
    return {
        "ok": True,
        "has_layout": True,
        "page": layout.get("page_key") or page_name,
        "image": image,
        "blocks": layout.get("blocks") or [],
        "stats": layout.get("stats") or {},
        "message": f"{len(layout.get('blocks') or [])} 个版面块",
    }


@router.get("/{patient_id}/ocr/pages/{page_name}/layout/hit")
def hit_ocr_layout(patient_id: str, page_name: str, q: str = ""):
    """在 layout 块中搜索文本（字段溯源）。"""
    from antigravity.engine.ocr_layout import find_layout_path, load_layout_json, hit_test_blocks
    p, _proj = find_patient(patient_id)
    if not p:
        raise HTTPException(404, "病人不存在")
    path = find_layout_path(p.ocr_dir, page_name)
    if not path:
        return {"hits": [], "has_layout": False}
    layout = load_layout_json(path) or {}
    return {"hits": hit_test_blocks(layout, q), "has_layout": True}


class OcrInputModeRequest(BaseModel):
    mode: Optional[str] = None  # auto | slices | full
    image_source: Optional[str] = None  # auto | preprocess | source


@router.put("/{patient_id}/ocr/input-mode")
def set_ocr_input_mode_api(patient_id: str, req: OcrInputModeRequest):
    """设置 OCR 结构模式与整页图源。"""
    from ..ocr_inputs import set_ocr_input_options, resolve_ocr_inputs
    p, _proj = find_patient(patient_id)
    if not p:
        raise HTTPException(404, "病人不存在")
    opts = set_ocr_input_options(p, mode=req.mode, image_source=req.image_source)
    p.mark_downstream_stale("ocr")
    p.save()
    plan = resolve_ocr_inputs(p)
    return {
        "ok": True,
        "mode": opts["input_mode"],
        "image_source": opts["image_source"],
        "effective_mode": plan["effective_mode"],
        "image_source_effective": plan.get("image_source_effective"),
        "image_source_label": plan.get("image_source_label"),
        "count": plan["count"],
        "message": plan["message"],
        "warning": plan["warning"],
        "error": plan.get("error") or "",
        "has_preprocess": plan.get("has_preprocess", False),
        "has_source": plan.get("has_source", False),
        "has_slices": plan.get("has_slices", False),
    }


@router.get("/{patient_id}/slice/base-image")
def get_slice_base_image(patient_id: str):
    """切片编辑应使用的底图阶段与列表（预处理优先）。"""
    from ..ocr_inputs import list_images, full_page_dir
    p, _proj = find_patient(patient_id)
    if not p:
        raise HTTPException(404, "病人不存在")
    root = full_page_dir(p)
    stage = "preprocess" if root == p.preprocess_dir else "source"
    images = []
    for f in list_images(root):
        try:
            rel = str(f.relative_to(root)).replace("\\", "/")
        except ValueError:
            rel = f.name
        images.append({"name": f.name, "relative": rel, "stage": stage})
    return {
        "stage": stage,
        "images": images,
        "count": len(images),
        "hint": "区域为病人级模板，套用到全部页（基于当前预处理图）" if stage == "preprocess"
        else "区域为病人级模板，套用到全部源图",
    }
