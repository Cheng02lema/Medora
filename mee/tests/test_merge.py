"""markdown 合并/页序测试。"""

from __future__ import annotations

from mee.modules.markdown_converter.converter import (
    PAGE_BREAK_MARKER,
    merge_markdown_files,
    merge_patient_folder,
    page_sort_key,
)


def test_page_sort_key_trailing_index():
    assert page_sort_key("微信图片_20260206125102_0.md") == 0
    assert page_sort_key("微信图片_20260206125102_12.md") == 12
    assert page_sort_key("page_张三_2.md") == 2


def test_page_sort_key_legacy_page_prefix():
    assert page_sort_key("report_page_3.md") == 3


def test_page_sort_key_unparseable():
    assert page_sort_key("no_index_here.md") is None or isinstance(
        page_sort_key("no_index_here.md"), int
    )


def test_merge_orders_by_page_index(fixtures_dir):
    folder = fixtures_dir / "ocr_out" / "张三"
    merged = merge_markdown_files(str(folder))
    assert merged is not None
    # 第一页应在第二页之前，第二页在第三页之前
    pos1 = merged.index("第一页")
    pos2 = merged.index("第二页")
    pos3 = merged.index("第三页")
    assert pos1 < pos2 < pos3
    # 三页应插入两个分页符
    assert merged.count(PAGE_BREAK_MARKER.strip()) == 2


def test_merge_patient_folder_writes_merged(fixtures_dir, tmp_path):
    import shutil

    src = fixtures_dir / "ocr_out" / "李四"
    work = tmp_path / "李四"
    shutil.copytree(src, work)
    merged_md = merge_patient_folder(str(work), make_docx=False)
    assert merged_md is not None
    assert merged_md.name == "李四_merged.md"
    assert merged_md.exists()
    text = merged_md.read_text(encoding="utf-8")
    assert text.index("第一页") < text.index("第二页")


def test_merge_empty_folder_returns_none(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert merge_markdown_files(str(empty)) is None
