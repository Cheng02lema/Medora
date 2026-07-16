"""antigravity backend 测试夹具：合成病人数据。"""

from __future__ import annotations

import pytest


@pytest.fixture
def sample_parent(tmp_path):
    """造一个父目录，内含两个病人子文件夹，每人几张合成图片。"""
    from PIL import Image

    parent = tmp_path / "病历"
    for name in ("张三", "李四"):
        d = parent / name
        d.mkdir(parents=True)
        for i in (1, 2):
            Image.new("RGB", (40, 30), (200, 200, 200)).save(d / f"{name}_{i}.jpg")
    return parent


@pytest.fixture
def workspace(tmp_path):
    return tmp_path / "workspace"


@pytest.fixture
def excel_template(tmp_path):
    """构造一份 Excel 表头模板 + json 字段配置，返回 json 路径。"""
    import json

    import openpyxl

    tpl = tmp_path / "t.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    for c, h in enumerate(["姓名", "住院号"], 1):
        ws.cell(1, c, h)
    wb.save(tpl)

    cfg = tmp_path / "t.json"
    cfg.write_text(json.dumps({
        "template_path": str(tpl),
        "fields": [{"column": "姓名", "type": "文本"}, {"column": "住院号", "type": "文本"}],
    }), encoding="utf-8")
    return cfg
