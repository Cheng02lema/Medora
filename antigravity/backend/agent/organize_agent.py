"""病例整理 Agent：DeepSeek/OpenAI function-calling loop + 规则回退。"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from .organize_session import OrganizeSession
from .tools_sandbox import (
    OPENAI_TOOLS,
    TOOL_SPECS,
    SandboxError,
    execute_tool,
    propose_layout,
    apply_layout,
    validate_layout,
    preview_tree,
    scan_images,
    scan_materials,
    split_by_page_count,
    pdf_to_images,
    pdf_info,
)

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "organize_system.md"


def load_system_prompt(extra: str = "") -> str:
    base = ""
    if PROMPT_PATH.is_file():
        base = PROMPT_PATH.read_text(encoding="utf-8")
    else:
        base = "你是病例整理助理。将材料整理为一人一文件夹图片目录后导入。"
    base += """

## PDF / 分页规则（必须遵守）
当用户说「一个 PDF 每 N 页一个病人」时，你必须按顺序调用工具，禁止只口头描述：
1. scan_materials 或 pdf_info
2. pdf_to_images（渲染到输出目录下的 _pages/ 子目录）
3. split_by_page_count(pages_per_patient=N, out_path=最终输出目录)
4. validate_layout
5. 向用户汇报病人数/每夹页数，询问是否导入

默认 pages_per_patient=2 当用户说「每两页」。
默认复制，不删除原 PDF。
"""
    if extra.strip():
        base += "\n\n## 用户附加指令\n" + extra.strip()
    return base


def _resolve_chat_url(llm_config: Dict[str, Any]) -> str:
    api_url = (llm_config.get("api_url") or llm_config.get("base_url") or "").rstrip("/")
    provider = (llm_config.get("provider") or "").strip()
    if not api_url and provider:
        try:
            from antigravity.engine.medical_extractor.engine import PROVIDER_DEFAULT_URLS
            api_url = (PROVIDER_DEFAULT_URLS.get(provider) or "").rstrip("/")
        except Exception:
            api_url = ""
    if not api_url and provider.lower() == "deepseek":
        api_url = "https://api.deepseek.com/v1/chat/completions"
    if not api_url:
        raise RuntimeError("未配置 Agent LLM 的 Base URL / Provider")
    # normalize
    if api_url.endswith("/chat/completions"):
        return api_url
    if api_url.endswith("/v1"):
        return api_url + "/chat/completions"
    if "/chat/completions" in api_url:
        return api_url
    return api_url.rstrip("/") + "/v1/chat/completions"


def llm_ready(llm_config: Optional[Dict[str, Any]]) -> bool:
    if not llm_config:
        return False
    if not llm_config.get("api_key"):
        return False
    if llm_config.get("api_url") or llm_config.get("base_url") or llm_config.get("provider"):
        return True
    return False


def _chat_completion(
    messages: List[Dict[str, Any]],
    llm_config: Dict[str, Any],
    tools: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """返回原始 message dict（可能含 tool_calls）。"""
    api_key = llm_config.get("api_key") or ""
    model = llm_config.get("model") or "deepseek-chat"
    if not api_key:
        raise RuntimeError("未配置 Agent LLM API Key")
    url = _resolve_chat_url(llm_config)
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": float(llm_config.get("temperature") if llm_config.get("temperature") is not None else 0.2),
        "max_tokens": int(llm_config.get("max_tokens") or 2000),
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    if resp.status_code != 200:
        raise RuntimeError(f"LLM HTTP {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    return data["choices"][0]["message"]


def _parse_text_tool_calls(text: str) -> List[Dict[str, Any]]:
    calls = []
    for m in re.finditer(r"TOOL_CALL\s*(\{.*?\})(?:\s|$)", text or "", re.S):
        try:
            obj = json.loads(m.group(1))
            if isinstance(obj, dict) and obj.get("name"):
                calls.append({"name": obj["name"], "arguments": obj.get("args") or obj.get("arguments") or {}})
        except json.JSONDecodeError:
            continue
    return calls


def _run_one_tool(
    name: str,
    args: Dict[str, Any],
    session: OrganizeSession,
    jail,
    confirm_apply: bool,
    user_message: str,
) -> Dict[str, Any]:
    args = dict(args or {})
    # defaults
    if name in ("scan_images", "scan_materials", "list_dir", "preview_tree"):
        args.setdefault("path", session.work_path)
    if name == "validate_layout":
        args.setdefault("out_path", session.out_path)
    if name == "propose_layout":
        args.setdefault("work_path", session.work_path)
        args.setdefault("out_path", session.out_path)
    if name == "pdf_to_images":
        args.setdefault("out_dir", str(Path(session.out_path) / "_pages" / Path(args.get("path") or "doc").stem))
        args.setdefault("dpi", 150)
    if name in ("split_by_page_count", "group_images_by_count"):
        args.setdefault("out_path", session.out_path)
        args.setdefault("pages_per_patient", 2)
        args.setdefault("name_prefix", "病人")
        args.setdefault("mode", "copy")
    if name == "apply_layout":
        if not args.get("plan") and session.plan:
            args["plan"] = session.plan
        if not confirm_apply and not any(k in (user_message or "") for k in ("确认", "执行", "apply")):
            return {"error": "需要用户确认后才能 apply_layout"}

    result = execute_tool(name, args, jail, session.work_path)
    if name == "propose_layout" and isinstance(result, dict):
        session.plan = result
    if name in ("split_by_page_count", "group_images_by_count") and isinstance(result, dict):
        # 记录为可导入计划摘要
        session.plan = {
            "out_path": result.get("out_path"),
            "patient_count": result.get("patient_count"),
            "file_count": result.get("source_pages") or sum(g.get("pages", 0) for g in result.get("groups") or []),
            "patients": result.get("patients") or [],
            "needs_confirm": False,
            "mode": result.get("mode") or "copy",
            "from_tool": name,
        }
    return result


def rule_based_turn(session: OrganizeSession, user_message: str) -> tuple:
    """无 LLM / 降级：支持 PDF 每 N 页 与简单扫描。"""
    jail = session.jail()
    msg = (user_message or "").strip()
    tool_results: List[Dict[str, Any]] = []

    # PDF 每 N 页
    m = re.search(r"每\s*(\d+)\s*页", msg) or re.search(r"(\d+)\s*页\s*一", msg)
    n_pages = int(m.group(1)) if m else (2 if any(k in msg for k in ("每两页", "每2页", "两页一个", "2页一个")) else None)
    if n_pages and any(k in msg.lower() for k in ("pdf", "拆", "切", "分页", "页")):
        mats = scan_materials(jail, session.work_path)
        tool_results.append({"name": "scan_materials", "result": {
            "image_count": mats["image_count"], "pdf_count": mats["pdf_count"],
            "pdfs": [{"name": p.get("name"), "page_count": p.get("page_count")} for p in mats.get("pdfs") or []],
        }})
        pdfs = [p for p in (mats.get("pdfs") or []) if p.get("page_count") and not p.get("error")]
        if not pdfs:
            return "工作目录里没找到可用 PDF。请确认路径下有 .pdf 文件。", tool_results
        # 处理第一个 PDF（多 PDF 可后续扩展）
        pdf_path = pdfs[0]["path"]
        pages_dir = str(Path(session.out_path) / "_pages" / Path(pdf_path).stem)
        rendered = pdf_to_images(jail, pdf_path, pages_dir, dpi=150)
        tool_results.append({"name": "pdf_to_images", "result": {
            "pdf": rendered["pdf"], "rendered": rendered["rendered"], "out_dir": rendered["out_dir"],
        }})
        split = split_by_page_count(
            jail,
            pages_dir=rendered["out_dir"],
            out_path=session.out_path,
            pages_per_patient=n_pages,
            name_prefix="病人",
            mode="copy",
        )
        tool_results.append({"name": "split_by_page_count", "result": {
            "patient_count": split["patient_count"],
            "pages_per_patient": split["pages_per_patient"],
            "patients": split["patients"][:20],
            "out_path": split["out_path"],
        }})
        session.plan = {
            "out_path": split["out_path"],
            "patient_count": split["patient_count"],
            "file_count": split["source_pages"],
            "patients": split["patients"],
            "needs_confirm": False,
            "mode": "copy",
            "from_tool": "split_by_page_count",
        }
        val = validate_layout(jail, session.out_path)
        tool_results.append({"name": "validate_layout", "result": val})
        tree = preview_tree(jail, session.out_path)
        tool_results.append({"name": "preview_tree", "result": {"tree": (tree.get("tree") or "")[:1200]}})
        text = (
            f"已按 **每 {n_pages} 页** 拆分 PDF「{Path(pdf_path).name}」：\n"
            f"- 渲染 {rendered['rendered']} 页\n"
            f"- 生成 **{split['patient_count']}** 个病人文件夹\n"
            f"- 输出：`{split['out_path']}`\n"
            f"- 校验：{val.get('message')}\n\n"
            f"可点击「导入到当前项目」。"
        )
        return text, tool_results

    if any(k in msg for k in ("扫描", "看看", "有什么", "scan", "列表", "目录", "材料")):
        r = scan_materials(jail, session.work_path)
        tool_results.append({"name": "scan_materials", "result": {
            "image_count": r["image_count"], "pdf_count": r["pdf_count"],
            "by_folder": r["by_folder"],
            "pdfs": [{"name": p.get("name"), "page_count": p.get("page_count"), "error": p.get("error")} for p in r.get("pdfs") or []],
        }})
        lines = [f"材料目录：图片 **{r['image_count']}** 张 · PDF **{r['pdf_count']}** 个"]
        for p in (r.get("pdfs") or [])[:10]:
            if p.get("error"):
                lines.append(f"- PDF {p.get('name')}: 错误 {p['error']}")
            else:
                lines.append(f"- PDF {p.get('name')}: {p.get('page_count')} 页")
        for k, v in list((r.get("by_folder") or {}).items())[:15]:
            lines.append(f"- 文件夹 {k}: {v} 张")
        lines.append("\n若 PDF 每两页一个病人，请直接说：**把 PDF 按每 2 页拆成病人**")
        return "\n".join(lines), tool_results

    if any(k in msg for k in ("计划", "整理", "propose", "方案", "分组")) and "页" not in msg:
        plan = propose_layout(jail, session.work_path, session.out_path)
        session.plan = plan
        tool_results.append({"name": "propose_layout", "result": {
            "patient_count": plan["patient_count"],
            "file_count": plan["file_count"],
            "patients": plan["patients"][:30],
            "needs_confirm": plan["needs_confirm"],
        }})
        return (
            f"已生成文件夹整理计划：{plan['patient_count']} 人 · {plan['file_count']} 张\n"
            f"病人：{', '.join(plan['patients'][:15])}\n"
            f"确认后回复 **确认执行**"
        ), tool_results

    if any(k in msg for k in ("确认执行", "执行计划", "apply", "开始复制")):
        if not session.plan:
            plan = propose_layout(jail, session.work_path, session.out_path)
            session.plan = plan
        # 若 plan 来自 split，已落盘，只需 validate
        if session.plan.get("from_tool") in ("split_by_page_count", "group_images_by_count"):
            val = validate_layout(jail, session.out_path)
            tool_results.append({"name": "validate_layout", "result": val})
            return f"分页结果已在输出目录。{val.get('message')}。可导入项目。", tool_results
        result = apply_layout(jail, session.plan, mode=session.plan.get("mode") or "copy")
        tool_results.append({"name": "apply_layout", "result": result})
        val = validate_layout(jail, session.out_path)
        tool_results.append({"name": "validate_layout", "result": val})
        return (
            f"已执行：成功 {result['copied_or_moved']}，失败 {result['error_count']}。{val.get('message')}"
        ), tool_results

    if any(k in msg for k in ("校验", "检查", "validate")):
        val = validate_layout(jail, session.out_path)
        tool_results.append({"name": "validate_layout", "result": val})
        return val.get("message") or json.dumps(val, ensure_ascii=False), tool_results

    r = scan_materials(jail, session.work_path)
    tool_results.append({"name": "scan_materials", "result": {
        "image_count": r["image_count"], "pdf_count": r["pdf_count"],
    }})
    return (
        f"已扫描：{r['image_count']} 张图 · {r['pdf_count']} 个 PDF。\n"
        "示例指令：\n"
        "- 扫描材料\n"
        "- 把 PDF 按每 2 页拆成病人\n"
        "- 生成计划 / 确认执行 / 校验"
    ), tool_results


def run_agent_turn(
    session: OrganizeSession,
    user_message: str,
    llm_config: Optional[Dict[str, Any]] = None,
    user_extra_prompt: str = "",
    max_steps: int = 12,
    confirm_apply: bool = False,
) -> Dict[str, Any]:
    session.status = "running"
    session.touch()
    session.messages.append({"role": "user", "content": user_message, "ts": time.time()})
    all_tool_logs: List[Dict[str, Any]] = []
    jail = session.jail()

    # 明确确认执行：规则路径
    if confirm_apply or (user_message or "").strip() in ("确认执行", "执行计划"):
        text, tools = rule_based_turn(session, "确认执行")
        for t in tools:
            entry = {"ts": time.time(), **t}
            session.tool_log.append(entry)
            all_tool_logs.append(entry)
        session.messages.append({"role": "assistant", "content": text, "ts": time.time()})
        session.status = "idle"
        session.touch()
        return {"reply": text, "tools": all_tool_logs, "session": session.to_public(), "mode": "rules"}

    use_llm = llm_ready(llm_config)

    # 确定性 PDF 规则：有「每N页」时先走规则工具链（更稳），再可选 LLM 润色
    if re.search(r"每\s*\d+\s*页|每两页|每2页|两页一个|2页一个", user_message or ""):
        text, tools = rule_based_turn(session, user_message)
        for t in tools:
            entry = {"ts": time.time(), **t}
            session.tool_log.append(entry)
            all_tool_logs.append(entry)
        session.messages.append({"role": "assistant", "content": text, "ts": time.time()})
        session.status = "idle"
        session.touch()
        return {"reply": text, "tools": all_tool_logs, "session": session.to_public(), "mode": "rules-pdf"}

    if not use_llm:
        text, tools = rule_based_turn(session, user_message)
        for t in tools:
            if t.get("name") == "propose_layout":
                try:
                    full = propose_layout(jail, session.work_path, session.out_path)
                    session.plan = full
                except Exception:
                    pass
            entry = {"ts": time.time(), **t}
            session.tool_log.append(entry)
            all_tool_logs.append(entry)
        session.messages.append({"role": "assistant", "content": text, "ts": time.time()})
        session.status = "idle"
        session.touch()
        return {"reply": text, "tools": all_tool_logs, "session": session.to_public(), "mode": "rules"}

    # —— LLM function-calling loop ——
    system = load_system_prompt(user_extra_prompt)
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system},
        {
            "role": "system",
            "content": f"工作目录: {session.work_path}\n输出目录: {session.out_path}\n请用 tools 完成任务。",
        },
    ]
    for m in session.messages[-10:]:
        if m["role"] in ("user", "assistant") and m.get("content"):
            messages.append({"role": m["role"], "content": m["content"][:4000]})

    final_text = ""
    for step in range(max_steps):
        try:
            msg = _chat_completion(messages, llm_config or {}, tools=OPENAI_TOOLS)
        except Exception as exc:
            text, tools = rule_based_turn(session, user_message)
            for t in tools:
                entry = {"ts": time.time(), **t}
                session.tool_log.append(entry)
                all_tool_logs.append(entry)
            final_text = f"（LLM 调用失败，已用规则模式）\n{text}\n\n详情: {exc}"
            break

        tool_calls = msg.get("tool_calls") or []
        content = msg.get("content") or ""

        # fallback 文本协议
        if not tool_calls and content:
            parsed = _parse_text_tool_calls(content)
            if parsed:
                tool_calls = [
                    {
                        "id": f"text_{i}",
                        "type": "function",
                        "function": {
                            "name": c["name"],
                            "arguments": json.dumps(c["arguments"], ensure_ascii=False),
                        },
                    }
                    for i, c in enumerate(parsed)
                ]

        if not tool_calls:
            final_text = re.sub(r"TOOL_CALL\s*\{.*?\}\s*", "", content, flags=re.S).strip() or content or "完成。"
            break

        # append assistant message with tool_calls
        messages.append({
            "role": "assistant",
            "content": content or None,
            "tool_calls": tool_calls,
        })

        for tc in tool_calls[:6]:
            fn = tc.get("function") or {}
            name = fn.get("name") or ""
            raw_args = fn.get("arguments") or "{}"
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
            except json.JSONDecodeError:
                args = {}
            try:
                result = _run_one_tool(name, args, session, jail, confirm_apply, user_message)
                # 压缩大结果
                log_result = result
                if isinstance(result, dict) and "mappings" in result:
                    log_result = {
                        "patient_count": result.get("patient_count"),
                        "file_count": result.get("file_count"),
                        "patients": (result.get("patients") or [])[:30],
                        "needs_confirm": result.get("needs_confirm"),
                    }
                if isinstance(result, dict) and "pages" in result and len(result.get("pages") or []) > 5:
                    log_result = {**result, "pages": (result.get("pages") or [])[:3], "pages_truncated": True}
            except Exception as exc:
                log_result = {"error": str(exc)}
            entry = {
                "ts": time.time(),
                "name": name,
                "args": {k: v for k, v in args.items() if k != "plan"},
                "result": log_result,
            }
            session.tool_log.append(entry)
            all_tool_logs.append(entry)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.get("id") or name,
                "content": json.dumps(log_result, ensure_ascii=False)[:6000],
            })
    else:
        final_text = final_text or "已达最大步骤，请根据工具结果继续指示或点击导入。"

    if not final_text:
        # 根据 tool log 生成摘要
        names = [t.get("name") for t in all_tool_logs]
        final_text = f"已执行工具：{', '.join(names) if names else '无'}。请查看计划/输出目录，或说「校验」。"

    session.messages.append({"role": "assistant", "content": final_text, "ts": time.time()})
    session.status = "idle"
    session.touch()
    return {
        "reply": final_text,
        "tools": all_tool_logs,
        "session": session.to_public(),
        "mode": "llm",
    }
