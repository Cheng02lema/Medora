"""用示例 OCR result.json 验证 layout 解析与落盘。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from antigravity.engine.ocr_layout import (
    extract_layout_pages,
    hit_test_blocks,
    save_layout_json,
    load_layout_json,
)
from antigravity.engine.ocr_client import save_layout_results

ROOT = Path(__file__).resolve().parents[3]
SAMPLE_DIR = ROOT / "示例" / "通过ocr大模型产生的md文档"


def _sample_files():
    if not SAMPLE_DIR.is_dir():
        return []
    return sorted(SAMPLE_DIR.rglob("*_result.json"))[:8]


@pytest.mark.skipif(not SAMPLE_DIR.is_dir(), reason="无示例 OCR JSON")
def test_extract_layout_from_real_samples():
    files = _sample_files()
    assert files, "应有示例 result.json"
    for fp in files:
        data = json.loads(fp.read_text(encoding="utf-8"))
        pages = extract_layout_pages(
            data,
            page_key=fp.stem.replace("_result", ""),
            image_meta={"stage": "source", "relative": fp.name, "name": fp.name},
        )
        assert pages, f"{fp.name} 应解析出至少一页"
        layout = pages[0]
        assert layout["image"]["width"] > 0
        assert layout["image"]["height"] > 0
        assert layout["stats"]["block_count"] >= 1
        for b in layout["blocks"]:
            assert len(b["bbox"]) == 4
            x1, y1, x2, y2 = b["bbox"]
            assert x2 > x1 and y2 > y1
            # 不严重越界
            assert x1 >= -2 and y1 >= -2
            assert x2 <= layout["image"]["width"] + 10
            assert y2 <= layout["image"]["height"] + 10


@pytest.mark.skipif(not SAMPLE_DIR.is_dir(), reason="无示例 OCR JSON")
def test_save_layout_results_writes_layout_json(tmp_path: Path):
    fp = _sample_files()[0]
    data = json.loads(fp.read_text(encoding="utf-8"))
    # save_layout_results 期望 list[result]
    results = [data] if isinstance(data, dict) else data
    base = tmp_path / "pageA"
    n = save_layout_results(
        results,
        base,
        save_layout=True,
        image_meta={"stage": "preprocess", "relative": "a.jpg", "name": "a.jpg"},
    )
    assert n >= 1
    layout_path = tmp_path / "pageA_0.layout.json"
    assert layout_path.is_file()
    layout = load_layout_json(layout_path)
    assert layout and layout["blocks"]
    assert layout["image"]["stage"] == "preprocess"
    md_path = tmp_path / "pageA_0.md"
    assert md_path.is_file()


@pytest.mark.skipif(not SAMPLE_DIR.is_dir(), reason="无示例 OCR JSON")
def test_hit_test_blocks():
    fp = SAMPLE_DIR / "宋思琪" / "微信图片_20260206091444_result.json"
    if not fp.is_file():
        fp = _sample_files()[0]
    data = json.loads(fp.read_text(encoding="utf-8"))
    pages = extract_layout_pages(data, page_key="t")
    layout = pages[0]
    # 找一个非空文本
    sample = next((b["text"] for b in layout["blocks"] if (b.get("text") or "").strip()), "")
    if not sample:
        pytest.skip("无文本块")
    needle = sample[: min(6, len(sample))]
    hits = hit_test_blocks(layout, needle)
    assert hits, f"应命中 {needle!r}"


def test_extract_empty_safe():
    assert extract_layout_pages({}) == []
    assert extract_layout_pages([]) == []
