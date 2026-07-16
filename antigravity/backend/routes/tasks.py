"""触发提取任务：批量（多个 patient_ids）或单个（一个 id）走同一接口。

任务在线程池里同步执行（内置 engine 同步逻辑），通过 WebSocket 广播
病人状态变化和任务完成汇总，不做细粒度步骤进度。
"""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..state import config, store
from ..tasks import TaskRunner
from ..ws import manager

router = APIRouter(prefix="/tasks", tags=["tasks"])

_executor = ThreadPoolExecutor(max_workers=2)
_task_summaries: Dict[str, dict] = {}


class ExtractRequest(BaseModel):
    patient_ids: List[str]


def _build_options() -> dict:
    ocr = config.data.get("ocr_api", {})
    extract = config.data.get("extract_llm", {})
    pipeline = config.data.get("pipeline", {})
    return {
        "enable_preprocess": pipeline.get("enable_preprocess", True),
        "enable_slice": pipeline.get("enable_slice", False),
        "enable_cleanup": pipeline.get("enable_cleanup", False),
        "ocr_url": ocr.get("url", ""),
        "ocr_model": ocr.get("model", ""),
        "ocr_preset": ocr.get("preset", "original"),
        "ocr_token": config.get_secret("ocr_api"),
        "extraction_template": pipeline.get("extraction_template", ""),
        "output_excel": pipeline.get("output_excel", ""),
        "extract_llm": {
            "provider": extract.get("provider", "DeepSeek"),
            "model": extract.get("model", ""),
            "base_url": extract.get("base_url", ""),
            "api_key": config.get_secret("extract_llm"),
        },
    }


def _on_update(patient, message: str):
    manager.broadcast_threadsafe({
        "type": "patient_update",
        "patient": patient.to_summary(),
        "message": message,
    })


def _run_task(task_id: str, patients: List):
    options = _build_options()
    runner = TaskRunner(patients, options, on_update=_on_update)
    summary = runner.run()
    _task_summaries[task_id] = summary
    manager.broadcast_threadsafe({"type": "task_done", "task_id": task_id, "summary": summary})


@router.post("/extract")
def start_extract(req: ExtractRequest):
    if not req.patient_ids:
        raise HTTPException(400, detail="未指定病人")
    patients = [store.get(pid) for pid in req.patient_ids]
    patients = [p for p in patients if p is not None]
    if not patients:
        raise HTTPException(404, detail="所选病人均不存在")
    task_id = uuid.uuid4().hex[:12]
    _task_summaries[task_id] = {"status": "running"}
    _executor.submit(_run_task, task_id, patients)
    return {"task_id": task_id, "patient_count": len(patients)}


@router.get("/{task_id}")
def get_task(task_id: str):
    summary = _task_summaries.get(task_id)
    if summary is None:
        raise HTTPException(404, detail="任务不存在")
    return summary
