"""流水线状态机测试：mock OCR/LLM，直接驱动 worker.run()（不起事件循环）。"""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mee.controllers.pipeline_controller import PipelineConfig, PipelineWorker


def _collect(worker):
    """把 step_completed 信号收集成 {key: (state, msg)}。"""
    events = {}
    worker.step_completed.connect(lambda key, state, msg: events.__setitem__(key, (state, msg)))
    finished = {}
    worker.finished.connect(lambda ok, msg: finished.update(success=ok, message=msg))
    return events, finished


def _base_config(tmp_path, ocr_out, template, **overrides):
    cfg = dict(
        scenario="image",
        raw_input=str(tmp_path / "raw"),
        preprocess_output=str(tmp_path / "pre"),
        ocr_output=str(ocr_out),
        api_url="http://ocr",
        api_token="tok",
        ocr_model="m",
        ocr_preset="original",
        file_extensions=[".jpg"],
        enable_payment_ocr=False,
        payment_pattern="-缴费情况.jpg",
        cleanup_target="",
        cleanup_pattern="*右表格_0.md",
        selected_steps=["merge", "extract", "export"],
        extraction_template=str(template),
        output_excel=str(tmp_path / "结果.xlsx"),
        extract_llm={"provider": "DeepSeek", "api_key": "k", "model": "m"},
    )
    cfg.update(overrides)
    return PipelineConfig(**cfg)


@pytest.fixture
def ocr_tree(fixtures_dir, tmp_path):
    """把合成 OCR 输出复制到临时目录，返回其路径。"""
    dst = tmp_path / "ocr_out"
    shutil.copytree(fixtures_dir / "ocr_out", dst)
    return dst


def test_merge_extract_export_happy_path(ocr_tree, fixtures_dir, tmp_path):
    template = fixtures_dir / "template_config.json"
    worker = PipelineWorker(_base_config(tmp_path, ocr_tree, template))
    events, finished = _collect(worker)

    fake_engine = MagicMock()
    fake_engine.extract.side_effect = lambda content, source="": {
        "姓名": source, "_source": source, "_status": "success",
    }
    with patch("mee.controllers.pipeline_controller.MedicalExtractionEngine", return_value=fake_engine):
        worker.run()

    assert events["merge"][0] == "success"
    assert events["extract"][0] == "success"
    assert events["export"][0] == "success"
    assert finished["success"] is True
    # 结果 Excel 已生成
    assert (tmp_path / "结果.xlsx").exists()


def test_critical_failure_aborts(ocr_tree, fixtures_dir, tmp_path):
    template = fixtures_dir / "template_config.json"
    worker = PipelineWorker(_base_config(tmp_path, ocr_tree, template))
    events, finished = _collect(worker)

    # 抽取引擎构造即抛错 -> extract 关键步骤失败 -> export 不应执行
    with patch("mee.controllers.pipeline_controller.MedicalExtractionEngine", side_effect=RuntimeError("boom")):
        worker.run()

    assert events["merge"][0] == "success"
    assert events["extract"][0] == "error"
    assert "export" not in events  # 关键步骤失败后中止，未到 export
    assert finished["success"] is False
    assert "中止" in finished["message"]


def test_text_scenario_skips_image_steps(tmp_path, fixtures_dir, ocr_tree):
    template = fixtures_dir / "template_config.json"
    cfg = _base_config(
        tmp_path, ocr_tree, template,
        scenario="text",
        selected_steps=["preprocess", "ocr_batch", "merge", "extract", "export"],
    )
    worker = PipelineWorker(cfg)
    events, finished = _collect(worker)

    fake_engine = MagicMock()
    fake_engine.extract.side_effect = lambda content, source="": {"_source": source, "_status": "success"}
    with patch("mee.controllers.pipeline_controller.MedicalExtractionEngine", return_value=fake_engine):
        worker.run()

    assert events["preprocess"][0] == "skipped"
    assert events["ocr_batch"][0] == "skipped"
    assert events["merge"][0] == "success"


def test_cancellation_stops_before_steps(ocr_tree, fixtures_dir, tmp_path):
    template = fixtures_dir / "template_config.json"
    worker = PipelineWorker(_base_config(tmp_path, ocr_tree, template))
    events, finished = _collect(worker)
    worker.stop()  # 运行前即请求停止

    with patch("mee.controllers.pipeline_controller.MedicalExtractionEngine"):
        worker.run()

    assert events["merge"][0] == "skipped"
    assert finished["success"] is False


def test_extract_isolates_single_patient_failure(ocr_tree, fixtures_dir, tmp_path):
    template = fixtures_dir / "template_config.json"
    worker = PipelineWorker(_base_config(tmp_path, ocr_tree, template))
    events, finished = _collect(worker)

    def _extract(content, source=""):
        if source == "李四":
            raise RuntimeError("模拟单个失败")
        return {"姓名": source, "_source": source, "_status": "success"}

    fake_engine = MagicMock()
    fake_engine.extract.side_effect = _extract
    with patch("mee.controllers.pipeline_controller.MedicalExtractionEngine", return_value=fake_engine):
        worker.run()

    # 一个病人失败不影响整体成功（仍有成功病人 + export 完成）
    assert events["extract"][0] == "success"
    assert events["export"][0] == "success"
    assert finished["success"] is True
