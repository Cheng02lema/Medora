"""病例整理 Agent API。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import WORKSPACE
from ..state import config, project_store
from ..ws import manager
from ..agent.organize_session import session_store
from ..agent.organize_agent import run_agent_turn, load_system_prompt
from ..agent.tools_sandbox import TOOL_SPECS, preview_tree, validate_layout, SandboxError

router = APIRouter(prefix="/agent/organize", tags=["agent-organize"])

PERSIST_ROOT = WORKSPACE / "_agent_organize"


def _llm_config() -> Dict[str, Any]:
    """病例整理 Agent 专用 LLM（agent_llm）。

    回落顺序：agent_llm → 环境变量 DEEPSEEK_API_KEY/AGENT_LLM_KEY → mee api_config.json
    （方便本机已有 DeepSeek 配置时直接可用；正式环境请在全局设置写 agent_llm）
    """
    try:
        llm = (config.data.get("agent_llm") or {}) if hasattr(config, "data") else {}
    except Exception:
        llm = {}
    api_key = ""
    try:
        api_key = config.get_secret("agent_llm") or ""
    except Exception:
        api_key = ""
    if not api_key:
        api_key = llm.get("api_key") or ""
    if not api_key:
        import os
        api_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("AGENT_LLM_KEY") or ""
    provider = llm.get("provider") or ""
    model = llm.get("model") or ""
    base = llm.get("base_url") or llm.get("api_url") or ""

    # 本机 mee 配置回落（仅当 agent 未配 key）
    if not api_key:
        try:
            from pathlib import Path
            mee = Path(__file__).resolve().parents[3] / "mee/modules/medical_extractor/api_config.json"
            if mee.is_file():
                import json
                d = json.loads(mee.read_text(encoding="utf-8"))
                api_key = d.get("api_key") or ""
                provider = provider or d.get("provider") or "DeepSeek"
                model = model if model and model != "gpt-4o-mini" else (d.get("model") or "deepseek-chat")
                base = base or (d.get("api_url") or "").replace("/chat/completions", "")
        except Exception:
            pass

    if not provider:
        provider = "DeepSeek"
    if not model or model == "gpt-4o-mini":
        model = "deepseek-chat" if "deepseek" in provider.lower() else model or "deepseek-chat"
    if not base and "deepseek" in provider.lower():
        base = "https://api.deepseek.com"

    return {
        "provider": provider,
        "api_url": base,
        "api_key": api_key,
        "model": model,
        "max_tokens": llm.get("max_tokens") or 2000,
        "temperature": llm.get("temperature") if llm.get("temperature") is not None else 0.2,
    }


class CreateSessionRequest(BaseModel):
    work_path: str
    out_path: Optional[str] = None
    project_id: Optional[str] = None


@router.post("/sessions")
def create_session(req: CreateSessionRequest):
    work = Path(req.work_path).expanduser()
    if not work.exists():
        raise HTTPException(400, f"工作目录不存在: {work}")
    out = Path(req.out_path).expanduser() if req.out_path else (work.parent / f"{work.name}_organized")
    try:
        sess = session_store.create(
            str(work),
            str(out),
            project_id=req.project_id or "",
            persist_root=PERSIST_ROOT,
        )
    except Exception as exc:
        raise HTTPException(400, str(exc))
    llm = _llm_config()
    return {
        "session": sess.to_public(),
        "system_prompt_preview": load_system_prompt()[:500],
        "tools": TOOL_SPECS,
        "llm_configured": bool(llm.get("api_key") and (llm.get("api_url") or llm.get("provider"))),
        "llm": {
            "provider": llm.get("provider") or "",
            "model": llm.get("model") or "",
            "configured": bool(llm.get("api_key")),
        },
    }


@router.get("/sessions/{session_id}")
def get_session(session_id: str):
    sess = session_store.get(session_id)
    if not sess:
        raise HTTPException(404, "会话不存在")
    return {
        "session": sess.to_public(),
        "messages": [m for m in sess.messages if m.get("role") in ("user", "assistant")][-50:],
        "tool_log": sess.tool_log[-40:],
        "plan": {
            "patient_count": (sess.plan or {}).get("patient_count"),
            "file_count": (sess.plan or {}).get("file_count"),
            "patients": (sess.plan or {}).get("patients"),
            "needs_confirm": (sess.plan or {}).get("needs_confirm"),
            "out_path": (sess.plan or {}).get("out_path"),
        } if sess.plan else None,
    }


class ChatRequest(BaseModel):
    message: str
    confirm_apply: bool = False
    extra_prompt: Optional[str] = None


@router.post("/sessions/{session_id}/chat")
def chat(session_id: str, req: ChatRequest):
    sess = session_store.get(session_id)
    if not sess:
        raise HTTPException(404, "会话不存在")
    if not (req.message or "").strip() and not req.confirm_apply:
        raise HTTPException(400, "消息为空")
    msg = req.message or ("确认执行" if req.confirm_apply else "")
    try:
        result = run_agent_turn(
            sess,
            msg,
            llm_config=_llm_config(),
            user_extra_prompt=req.extra_prompt or "",
            confirm_apply=req.confirm_apply,
        )
    except SandboxError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        sess.status = "error"
        raise HTTPException(500, f"Agent 失败: {exc}")
    try:
        sess.save(PERSIST_ROOT)
    except Exception:
        pass
    return result


@router.get("/sessions/{session_id}/tree")
def get_tree(session_id: str, which: str = "out"):
    sess = session_store.get(session_id)
    if not sess:
        raise HTTPException(404, "会话不存在")
    path = sess.out_path if which == "out" else sess.work_path
    try:
        tree = preview_tree(sess.jail(), path)
        val = validate_layout(sess.jail(), sess.out_path) if which == "out" else None
    except SandboxError as exc:
        raise HTTPException(400, str(exc))
    return {"tree": tree, "validate": val}


class ImportRequest(BaseModel):
    project_id: Optional[str] = None


@router.post("/sessions/{session_id}/import")
def import_session(session_id: str, req: ImportRequest):
    sess = session_store.get(session_id)
    if not sess:
        raise HTTPException(404, "会话不存在")
    project_id = req.project_id or sess.project_id
    if not project_id:
        raise HTTPException(400, "未指定项目")
    proj = project_store.get(project_id)
    if not proj:
        raise HTTPException(404, "项目不存在")
    try:
        val = validate_layout(sess.jail(), sess.out_path)
    except SandboxError as exc:
        raise HTTPException(400, str(exc))
    if not val.get("import_ready"):
        raise HTTPException(400, val.get("message") or "输出目录不可导入")
    added = proj.import_image_folder(sess.out_path)
    if not added:
        raise HTTPException(400, "导入失败：未找到含图片的病人文件夹")
    for pat in added:
        manager.emit_patient_update(pat.to_summary())
    return {
        "ok": True,
        "imported": len(added),
        "patients": [p.to_summary() for p in added],
        "message": f"已导入 {len(added)} 位病人",
    }


@router.get("/prompt")
def get_prompt():
    return {"text": load_system_prompt(), "path": str(
        Path(__file__).resolve().parent.parent / "agent" / "prompts" / "organize_system.md"
    )}


@router.get("/tools")
def list_tools():
    return {"tools": TOOL_SPECS}
