"""导出 API：把抽取结果写入 Excel。"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..state import config, find_patient, project_store
from ..stage_runner import StageRunner
from ..ws import manager

router = APIRouter(prefix="/export", tags=["export"])


class ExportRequest(BaseModel):
    patient_ids: List[str]
    output_path: str
    project_id: Optional[str] = None


def _export_settings(patient_ids: List[str], project_id: Optional[str] = None) -> dict:
    """优先用项目模板；否则全局 pipeline 模板。"""
    project = None
    if project_id:
        project = project_store.get(project_id)
    if project is None and patient_ids:
        _, project = find_patient(patient_ids[0])
    if project is not None:
        return {
            "extraction_template": project.extraction_template or config.data.get("pipeline", {}).get("extraction_template", ""),
            "output_excel": project.output_excel or "",
            "ocr_token": "",
        }
    return {
        "extraction_template": config.data.get("pipeline", {}).get("extraction_template", ""),
        "output_excel": config.data.get("pipeline", {}).get("output_excel", ""),
        "ocr_token": "",
    }


@router.post("/excel")
def export_excel(req: ExportRequest):
    """把指定病人的抽取结果导出为 Excel。"""
    patients = [find_patient(pid)[0] for pid in req.patient_ids]
    patients = [p for p in patients if p is not None]
    if not patients:
        raise HTTPException(404, "所选病人均不存在")

    settings = _export_settings(req.patient_ids, req.project_id)
    if not settings.get("extraction_template"):
        raise HTTPException(400, "未配置抽取模板：请在项目设置中指定 Excel 模板")

    runner = StageRunner(settings)
    try:
        path = runner.run_export(patients, req.output_path)
    except Exception as exc:
        raise HTTPException(400, str(exc))

    for p in patients:
        p.stages["export"].mark_done()
        p.save()
        manager.emit_patient_update(p.to_summary())

    return {"path": path, "row_count": len(patients)}


@router.get("/preview")
def export_preview(patient_ids: str = "", project_id: str = ""):
    """导出预览：返回指定病人的抽取结果摘要。"""
    ids = [pid.strip() for pid in patient_ids.split(",") if pid.strip()]
    if not ids:
        # 当前项目或全局所有已抽取病人
        if project_id:
            project = project_store.get(project_id)
            if project:
                ids = [p.id for p in project.patient_store.all() if p.get_extracted_fields()]
        if not ids:
            ids = [p.id for p in _all_patients() if p.get_extracted_fields()]

    result = []
    for pid in ids:
        p, _ = find_patient(pid)
        if not p:
            continue
        fields = p.get_extracted_fields()
        if not fields:
            continue
        row = fields.get("fields", {})
        flat = {}
        for k, v in row.items():
            if isinstance(v, dict) and "value" in v:
                flat[k] = v["value"]
            else:
                flat[k] = v
        result.append({
            "id": p.id,
            "name": p.name,
            "fields": flat,
            "review_status": p.stages["review"].status,
        })
    return result


def _all_patients():
    patients = []
    for proj in project_store.all():
        patients.extend(proj.patient_store.all())
    return patients
