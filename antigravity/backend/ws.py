"""WebSocket 连接管理：广播阶段进度、日志、状态更新。

TaskRunner/stage_runner 跑在线程池里（同步代码），用 asyncio.run_coroutine_threadsafe
把更新从工作线程安全地送回事件循环再广播给所有连接的客户端。
"""

from __future__ import annotations

import asyncio
import logging
from typing import List

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self.active: List[WebSocket] = []
        self.loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def _broadcast(self, message: dict):
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    def broadcast_threadsafe(self, message: dict):
        """从任意线程（包括线程池里的 StageRunner）安全地广播。"""
        if not self.loop:
            return
        try:
            asyncio.run_coroutine_threadsafe(self._broadcast(message), self.loop)
        except RuntimeError:
            logger.debug("事件循环已关闭，跳过广播")

    # ---- 便捷方法 ----
    def emit_stage_started(self, patient_id: str, stage: str, task_id: str = ""):
        self.broadcast_threadsafe({
            "type": "stage_started",
            "patient_id": patient_id,
            "stage": stage,
            "task_id": task_id,
        })

    def emit_stage_progress(self, patient_id: str, stage: str, current: int, total: int, message: str):
        self.broadcast_threadsafe({
            "type": "stage_progress",
            "patient_id": patient_id,
            "stage": stage,
            "current": current,
            "total": total,
            "message": message,
        })

    def emit_stage_done(self, patient_id: str, stage: str, status: str, message: str):
        self.broadcast_threadsafe({
            "type": "stage_done",
            "patient_id": patient_id,
            "stage": stage,
            "status": status,
            "message": message,
        })

    def emit_log(self, patient_id: str, stage: str, level: str, message: str):
        self.broadcast_threadsafe({
            "type": "log",
            "patient_id": patient_id,
            "stage": stage,
            "level": level,
            "message": message,
            "timestamp": None,
        })

    def emit_patient_update(self, patient_summary: dict):
        self.broadcast_threadsafe({
            "type": "patient_update",
            "patient": patient_summary,
        })

    def emit_task_done(self, task_id: str, summary: dict):
        self.broadcast_threadsafe({
            "type": "task_done",
            "task_id": task_id,
            "summary": summary,
        })

    def emit_ocr_page_done(self, patient_id: str, page: dict, current: int, total: int):
        """OCR 单页成功：前端可增量插入卡片。"""
        self.broadcast_threadsafe({
            "type": "ocr_page_done",
            "patient_id": patient_id,
            "page": page,
            "current": current,
            "total": total,
        })

    def emit_ocr_page_error(self, patient_id: str, page_name: str, error: str, current: int, total: int):
        self.broadcast_threadsafe({
            "type": "ocr_page_error",
            "patient_id": patient_id,
            "page_name": page_name,
            "error": error,
            "current": current,
            "total": total,
        })

    def emit_pipeline_started(self, project_id: str, task_id: str, patient_ids: list, stages: list):
        self.broadcast_threadsafe({
            "type": "pipeline_started",
            "project_id": project_id,
            "task_id": task_id,
            "patient_ids": patient_ids,
            "stages": stages,
        })

    def emit_pipeline_done(self, project_id: str, task_id: str, summary: dict):
        self.broadcast_threadsafe({
            "type": "pipeline_done",
            "project_id": project_id,
            "task_id": task_id,
            "summary": summary,
        })


manager = ConnectionManager()
