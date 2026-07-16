"""项目级批量流水线：可选多步骤、多病人串行执行。"""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..patient import STAGE_ORDER
from ..state import config, project_store
from ..stage_runner import StageRunner
from ..ws import manager
from .stages import _build_settings_for_patient, _make_callbacks

router = APIRouter(prefix="/projects", tags=["pipeline"])

_executor = ThreadPoolExecutor(max_workers=1)
_pipeline_runners: Dict[str, StageRunner] = {}


# 可批量执行的阶段（不含 source/review）
PIPELINEABLE = [s for s in STAGE_ORDER if s not in ("source", "review")]


class PipelineRunRequest(BaseModel):
    patient_ids: Optional[List[str]] = None  # None = 项目全部
    stages: List[str] = ["preprocess", "ocr", "merge", "extract"]
    fail_policy: str = "continue"  # continue | stop
    only_pending: bool = False
    rerun: bool = False


@router.post("/{project_id}/pipeline/run")
def run_project_pipeline(project_id: str, req: PipelineRunRequest):
    project = project_store.get(project_id)
    if not project:
        raise HTTPException(404, "项目不存在")

    stages = [s for s in req.stages if s in PIPELINEABLE]
    if not stages:
        raise HTTPException(400, f"请至少选择一个有效步骤：{PIPELINEABLE}")

    all_patients = project.patient_store.all()
    if req.patient_ids:
        id_set = set(req.patient_ids)
        patients = [p for p in all_patients if p.id in id_set]
    else:
        patients = list(all_patients)

    if req.only_pending:
        patients = [p for p in patients if p.overall_status() in ("pending", "error", "stale")]

    if not patients:
        raise HTTPException(400, "没有可执行的病人")

    task_id = uuid.uuid4().hex[:12]
    # 用第一个病人构建 settings（项目级配置相同）
    settings = _build_settings_for_patient(patients[0], project)
    on_progress, on_log, on_stage_done, on_ocr_page = _make_callbacks(task_id)
    runner = StageRunner(settings, on_progress, on_log, on_stage_done, on_ocr_page)
    _pipeline_runners[task_id] = runner

    patient_ids = [p.id for p in patients]
    manager.emit_pipeline_started(project_id, task_id, patient_ids, stages)

    def _run():
        done_patients = 0
        error_patients = 0
        stage_stats: Dict[str, Dict[str, int]] = {
            s: {"done": 0, "error": 0, "skipped": 0} for s in stages
        }
        try:
            for patient in patients:
                if runner.is_stopped:
                    break
                patient_failed = False
                for stage in stages:
                    if runner.is_stopped:
                        break
                    # 文本/Excel 源自动跳过图像阶段
                    ds = patient.stages["source"].data.get("data_source", "image")
                    if ds in ("text", "excel") and stage in ("preprocess", "slice", "ocr"):
                        patient.stages[stage].mark_skipped(f"数据源 {ds}")
                        patient.save()
                        manager.emit_stage_done(patient.id, stage, "skipped", f"数据源 {ds}，跳过")
                        stage_stats[stage]["skipped"] += 1
                        manager.emit_patient_update(patient.to_summary())
                        continue

                    manager.emit_stage_started(patient.id, stage)
                    try:
                        runner.run_single(patient, stage, rerun=req.rerun)
                        st = patient.stages[stage].status
                        if st == "done":
                            stage_stats[stage]["done"] += 1
                        elif st == "skipped":
                            stage_stats[stage]["skipped"] += 1
                        elif st == "error":
                            stage_stats[stage]["error"] += 1
                            patient_failed = True
                    except Exception as exc:
                        stage_stats[stage]["error"] += 1
                        patient_failed = True
                        manager.emit_log(patient.id, stage, "error", str(exc))
                        if req.fail_policy == "stop":
                            runner.stop()
                            break
                    if patient_failed and req.fail_policy == "stop":
                        break
                if patient_failed:
                    error_patients += 1
                else:
                    done_patients += 1
                manager.emit_patient_update(patient.to_summary())
        finally:
            _pipeline_runners.pop(task_id, None)
            summary = {
                "done_patients": done_patients,
                "error_patients": error_patients,
                "total_patients": len(patients),
                "stages": stage_stats,
                "stopped": runner.is_stopped,
            }
            manager.emit_pipeline_done(project_id, task_id, summary)
            manager.emit_task_done(task_id, {
                "done": done_patients,
                "error": error_patients,
                "stages": stage_stats,
            })

    _executor.submit(_run)
    return {
        "task_id": task_id,
        "patient_count": len(patients),
        "stages": stages,
    }


@router.post("/{project_id}/pipeline/stop")
def stop_project_pipeline(project_id: str, task_id: str = ""):
    """停止项目流水线。task_id 为空则停所有。"""
    if task_id:
        runner = _pipeline_runners.get(task_id)
        if not runner:
            raise HTTPException(404, "任务不存在或已完成")
        runner.stop()
        return {"ok": True}
    for runner in list(_pipeline_runners.values()):
        runner.stop()
    return {"ok": True, "stopped": len(_pipeline_runners)}


@router.get("/pipeline-meta/stages")
def list_pipelineable_stages():
    """可批量执行的步骤列表（避免与 /{project_id} 路由冲突）。"""
    return {
        "stages": [
            {"key": s, "label": {
                "preprocess": "预处理", "slice": "切片", "ocr": "OCR",
                "merge": "合并", "extract": "抽取", "export": "导出",
            }.get(s, s)}
            for s in PIPELINEABLE
        ]
    }
