#!/usr/bin/env python3
"""离线测试：PDF 每 2 页拆病人 + DeepSeek agent_llm（若有 key）。

用法:
  cd 数据提取
  python3 antigravity/scripts/test_organize_agent.py

可选环境变量:
  DEEPSEEK_API_KEY=sk-...
  AGENT_LLM_KEY=sk-...
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def make_sample_pdf(path: Path, pages: int = 6) -> None:
    import fitz
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=400, height=600)
        page.insert_text((72, 72), f"Sample page {i + 1}/{pages}", fontsize=16)
        page.insert_text((72, 120), f"Patient group {(i // 2) + 1}", fontsize=12)
    doc.save(str(path))
    doc.close()


def load_agent_llm() -> dict:
    """优先环境变量，其次 medora agent_llm，再次 mee api_config / extract。"""
    key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("AGENT_LLM_KEY") or ""
    provider = "DeepSeek"
    model = "deepseek-chat"
    base = "https://api.deepseek.com"
    try:
        from antigravity.engine.config_manager import ConfigManager
        c = ConfigManager()
        ag = c.data.get("agent_llm") or {}
        if not key:
            key = c.get_secret("agent_llm") or ""
        if ag.get("provider"):
            provider = ag["provider"]
        if ag.get("model"):
            model = ag["model"]
        if ag.get("base_url"):
            base = ag["base_url"]
        if not key:
            key = c.get_secret("extract_llm") or ""
    except Exception as exc:
        print("config load warn:", exc)

    if not key:
        # mee legacy
        mee = ROOT / "mee/modules/medical_extractor/api_config.json"
        if mee.is_file():
            d = json.loads(mee.read_text(encoding="utf-8"))
            key = d.get("api_key") or ""
            model = d.get("model") or model
            base = (d.get("api_url") or base).replace("/chat/completions", "")
            if base.endswith("/v1"):
                pass
            provider = d.get("provider") or provider
            print("using mee api_config.json for key")

    return {
        "provider": provider,
        "api_key": key,
        "api_url": base,
        "model": model if model != "gpt-4o-mini" else "deepseek-chat",
        "temperature": 0.2,
        "max_tokens": 2000,
    }


def test_tools_pdf_split() -> None:
    from antigravity.backend.agent.tools_sandbox import (
        PathJail,
        pdf_to_images,
        split_by_page_count,
        validate_layout,
    )

    td = Path(tempfile.mkdtemp(prefix="medora_org_"))
    try:
        work = td / "work"
        out = td / "out"
        work.mkdir()
        out.mkdir()
        pdf = work / "bundle.pdf"
        make_sample_pdf(pdf, 6)
        jail = PathJail([work, out])
        pages_dir = out / "_pages" / "bundle"
        rendered = pdf_to_images(jail, str(pdf), str(pages_dir), dpi=100)
        assert rendered["rendered"] == 6, rendered
        split = split_by_page_count(
            jail,
            pages_dir=str(pages_dir),
            out_path=str(out),
            pages_per_patient=2,
            name_prefix="病人",
        )
        assert split["patient_count"] == 3, split
        assert split["patients"] == ["病人_001", "病人_002", "病人_003"], split
        # each folder 2 images
        for p in split["patients"]:
            imgs = list((out / p).glob("*"))
            assert len(imgs) == 2, (p, imgs)
        val = validate_layout(jail, str(out))
        assert val["ok"], val
        print("[PASS] tools pdf split 6 pages -> 3 patients x 2")
    finally:
        shutil.rmtree(td, ignore_errors=True)


def test_rule_agent_pdf() -> None:
    from antigravity.backend.agent.organize_session import OrganizeSession
    from antigravity.backend.agent.organize_agent import run_agent_turn

    td = Path(tempfile.mkdtemp(prefix="medora_org_"))
    try:
        work = td / "work"
        out = td / "out"
        work.mkdir()
        out.mkdir()
        make_sample_pdf(work / "bundle.pdf", 6)
        sess = OrganizeSession(
            id="test",
            work_path=str(work),
            out_path=str(out),
        )
        r = run_agent_turn(
            sess,
            "把目录里的 PDF 按每 2 页拆成一个病人，复制到输出目录",
            llm_config=None,  # force rules-pdf path
            max_steps=8,
        )
        print("mode:", r.get("mode"))
        print("reply:", (r.get("reply") or "")[:300])
        print("tools:", [t.get("name") for t in r.get("tools") or []])
        assert any(t.get("name") == "pdf_to_images" for t in r.get("tools") or []), r
        assert any(t.get("name") == "split_by_page_count" for t in r.get("tools") or []), r
        patients = list(out.glob("病人_*"))
        # _pages also under out
        patients = [p for p in out.iterdir() if p.is_dir() and p.name.startswith("病人_")]
        assert len(patients) == 3, list(out.iterdir())
        print("[PASS] rule agent pdf 每2页")
    finally:
        shutil.rmtree(td, ignore_errors=True)


def test_llm_agent_pdf(llm: dict) -> None:
    from antigravity.backend.agent.organize_session import OrganizeSession
    from antigravity.backend.agent.organize_agent import run_agent_turn, llm_ready

    if not llm_ready(llm):
        print("[SKIP] LLM agent: no api key")
        return

    td = Path(tempfile.mkdtemp(prefix="medora_org_"))
    try:
        work = td / "work"
        out = td / "out"
        work.mkdir()
        out.mkdir()
        make_sample_pdf(work / "cases.pdf", 6)
        sess = OrganizeSession(id="llmtest", work_path=str(work), out_path=str(out))
        # 用不会被 rules-pdf 短路的措辞？实际上「每 2 页」会走 rules-pdf。
        # 额外测一次 LLM 扫描理解：
        r1 = run_agent_turn(sess, "先扫描一下这个目录有什么材料", llm_config=llm, max_steps=6)
        print("LLM scan mode:", r1.get("mode"))
        print("LLM scan reply:", (r1.get("reply") or "")[:400])
        print("LLM scan tools:", [t.get("name") for t in r1.get("tools") or []])

        # PDF 规则路径（确定性，「每 2 页」短路）
        r2 = run_agent_turn(
            sess,
            "请把 PDF 每 2 页拆成一个病人文件夹",
            llm_config=llm,
            max_steps=10,
        )
        print("PDF split mode:", r2.get("mode"))
        print("PDF split tools:", [t.get("name") for t in r2.get("tools") or []])
        patients = [p for p in out.iterdir() if p.is_dir() and p.name.startswith("病人_")]
        assert len(patients) == 3, list(out.iterdir())
        print("[PASS] LLM+rules pdf pipeline")

        # 纯 LLM function-calling（避免「每N页」规则短路）
        td2 = Path(tempfile.mkdtemp(prefix="medora_org_pure_"))
        try:
            w2, o2 = td2 / "work", td2 / "out"
            w2.mkdir()
            o2.mkdir()
            make_sample_pdf(w2 / "cases.pdf", 6)
            sess2 = OrganizeSession(id="purellm", work_path=str(w2), out_path=str(o2))
            r3 = run_agent_turn(
                sess2,
                "请用工具把 cases.pdf 渲染成图片，再按 pages_per_patient=2 分组到输出目录并校验。必须调用工具。",
                llm_config=llm,
                max_steps=12,
            )
            print("Pure LLM mode:", r3.get("mode"))
            print("Pure LLM tools:", [t.get("name") for t in r3.get("tools") or []])
            assert r3.get("mode") == "llm", r3
            names = [t.get("name") for t in r3.get("tools") or []]
            assert "pdf_to_images" in names and "split_by_page_count" in names, names
            pure_patients = [p for p in o2.iterdir() if p.is_dir() and p.name.startswith("病人_")]
            assert len(pure_patients) == 3, list(o2.iterdir())
            print("[PASS] pure LLM function-calling pdf pipeline")
        finally:
            shutil.rmtree(td2, ignore_errors=True)
    finally:
        shutil.rmtree(td, ignore_errors=True)


def test_deepseek_ping(llm: dict) -> None:
    from antigravity.backend.agent.organize_agent import _chat_completion, llm_ready
    if not llm_ready(llm):
        print("[SKIP] deepseek ping: no key")
        return
    msg = _chat_completion(
        [{"role": "user", "content": "只回复：pong"}],
        llm,
        tools=None,
    )
    content = (msg.get("content") or "").strip()
    print("DeepSeek ping:", content[:100])
    assert content, msg
    print("[PASS] DeepSeek chat ok, model=", llm.get("model"))


def main() -> int:
    print("=== 1) deterministic PDF tools ===")
    test_tools_pdf_split()

    print("\n=== 2) rule agent PDF path ===")
    test_rule_agent_pdf()

    print("\n=== 3) DeepSeek config ===")
    llm = load_agent_llm()
    print("provider:", llm.get("provider"), "model:", llm.get("model"), "key:", bool(llm.get("api_key")))

    print("\n=== 4) DeepSeek ping ===")
    test_deepseek_ping(llm)

    print("\n=== 5) agent with LLM ===")
    test_llm_agent_pdf(llm)

    print("\nALL DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
