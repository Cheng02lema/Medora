"""旧版外置工具 API（已废弃）。

切片/遮罩已全部内置到前端，不再启动 PyQt 子进程。
保留路由以免旧客户端 404，统一返回 gone。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("/status")
def tools_status():
    return {}


@router.post("/launch/{tool}")
def launch_tool(tool: str):
    raise HTTPException(
        410,
        f"外置工具「{tool}」已移除：请使用应用内切片/遮罩功能",
    )


@router.post("/stop/{tool}")
def stop_tool(tool: str):
    return {"ok": True, "message": "无外置工具在运行"}
