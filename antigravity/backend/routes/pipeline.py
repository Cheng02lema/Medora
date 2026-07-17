"""项目级批量流水线：可选多步骤；病人级可并行，单人阶段仍串行。"""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..patient import STAGE_ORDER
from ..state import config, project_store
from ..stage_runner import StageRunner
from ..ws import manager
from .stages import _build_settings_for_patient, _make_callbacks

router = APIRouter(prefix="/projects", tags=["pipeline"])

# 同时只跑一条流水线任务（任务内部再按 N 并行病人）
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


def _run_one_patient_pipeline(
    runner: StageRunner,
    patient,
    stages: List[str],
    rerun: bool,
    fail_policy: str,
    stage_stats: Dict[str, Dict[str, int]],
    stats_lock: threading.Lock,
) -> bool:
    """跑完一个病人的全部阶段。返回 True=有失败。"""
    patient_failed = False
    for stage in stages:
        if runner.is_stopped:
            break
        ds = patient.stages["source"].data.get("data_source", "image")
        if ds in ("text", "excel") and stage in ("preprocess", "slice", "ocr"):
            patient.stages[stage].mark_skipped(f"数据源 {ds}")
            patient.save()
            manager.emit_stage_done(patient.id, stage, "skipped", f"数据源 {ds}，跳过")
            with stats_lock:
                stage_stats[stage]["skipped"] += 1
            manager.emit_patient_update(patient.to_summary())
            continue

        manager.emit_stage_started(patient.id, stage)
        try:
            runner.run_single(patient, stage, rerun=rerun)
            st = patient.stages[stage].status
            with stats_lock:
                if st == "done":
                    stage_stats[stage]["done"] += 1
                elif st == "skipped":
                    stage_stats[stage]["skipped"] += 1
                elif st == "error":
                    stage_stats[stage]["error"] += 1
                    patient_failed = True
        except Exception as exc:
            with stats_lock:
                stage_stats[stage]["error"] += 1
            patient_failed = True
            manager.emit_log(patient.id, stage, "error", str(exc))
            if fail_policy == "stop":
                runner.stop()
                break
        if patient_failed and fail_policy == "stop":
            runner.stop()
            break
    manager.emit_patient_update(patient.to_summary())
    return patient_failed


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
    settings = _build_settings_for_patient(patients[0], project)
    on_progress, on_log, on_stage_done, on_ocr_page = _make_callbacks(task_id)
    runner = StageRunner(settings, on_progress, on_log, on_stage_done, on_ocr_page)
    _pipeline_runners[task_id] = runner

    from ..config_resolve import clamp_parallel_patients
    parallel = clamp_parallel_patients(settings.get("max_parallel_patients", 1), 1)
    parallel = min(parallel, len(patients))

    patient_ids = [p.id for p in patients]
    manager.emit_pipeline_started(project_id, task_id, patient_ids, stages)

    def _run():
        done_patients = 0
        error_patients = 0
        stage_stats: Dict[str, Dict[str, int]] = {
            s: {"done": 0, "error": 0, "skipped": 0} for s in stages
        }
        stats_lock = threading.Lock()
        try:
            if parallel <= 1:
                for patient in patients:
                    if runner.is_stopped:
                        break
                    failed = _run_one_patient_pipeline(
                        runner, patient, stages, req.rerun, req.fail_policy, stage_stats, stats_lock,
                    )
                    if failed:
                        error_patients += 1
                    else:
                        done_patients += 1
            else:
                runner.on_log(
                    "", stages[0], "info",
                    f"批量加速：同时处理 {parallel} 人 · 共 {len(patients)} 人",
                )
                with ThreadPoolExecutor(max_workers=parallel) as pool:
                    futures = {}
                    for patient in patients:
                        if runner.is_stopped:
                            break
                        fut = pool.submit(
                            _run_one_patient_pipeline,
                            runner, patient, stages, req.rerun, req.fail_policy, stage_stats, stats_lock,
                        )
                        futures[fut] = patient
                    for fut in as_completed(futures):
                        try:
                            failed = fut.result()
                        except Exception:
                            failed = True
                        if failed:
                            error_patients += 1
                        else:
                            done_patients += 1
        finally:
            _pipeline_runners.pop(task_id, None)
            summary = {
                "done_patients": done_patients,
                "error_patients": error_patients,
                "total_patients": len(patients),
                "stages": stage_stats,
                "stopped": runner.is_stopped,
                "parallel": parallel,
            }
            manager.emit_pipeline_done(project_id, task_id, summary)
            manager.emit_task_done(task_id, {
                "done": done_patients,
                "error": error_patients,
                "stages": stage_stats,
                "parallel": parallel,
            })

    _executor.submit(_run)
    return {
        "task_id": task_id,
        "patient_count": len(patients),
        "stages": stages,
        "parallel": parallel,
    }


@router.post("/{project_id}/pipeline/stop")
def stop_project_pipeline(project_id: str, task_id: str = ""):
    """停止项目流水线。已在处理的病人会做完当前阶段；不再开新病人。"""
    if task_id:
        runner = _pipeline_runners.get(task_id)
        if not runner:
            raise HTTPException(404, "任务不存在或已完成")
        runner.stop()
        return {"ok": True, "message": "正在停止：已在处理的病人会做完当前阶段"}
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
