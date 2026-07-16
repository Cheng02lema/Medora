"""抽取引擎测试（mock 掉 requests，不发真实请求）。"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from mee.modules.medical_extractor.engine import (
    ClaudeClient,
    MedicalExtractionEngine,
    OpenAICompatibleClient,
    create_api_client,
    load_template_config,
)


def _tpl_config():
    return {
        "fields": [
            {"column": "姓名", "description": "患者姓名", "type": "文本"},
            {"column": "年龄", "description": "年龄", "type": "整数"},
        ],
        "emr_format": "测试",
    }


def test_create_api_client_provider_dispatch():
    assert isinstance(create_api_client({"provider": "DeepSeek", "model": "m", "api_key": "k"}), OpenAICompatibleClient)
    assert isinstance(create_api_client({"provider": "Claude", "model": "m", "api_key": "k"}), ClaudeClient)
    # 未知 provider 回落到 OpenAI 兼容
    assert isinstance(create_api_client({"provider": "自定义", "model": "m", "api_key": "k", "api_url": "http://x"}), OpenAICompatibleClient)


def test_create_api_client_fills_default_url():
    client = create_api_client({"provider": "DeepSeek", "model": "m", "api_key": "k"})
    assert "deepseek" in client.config["api_url"]


def test_build_prompt_contains_all_fields():
    engine = MedicalExtractionEngine({"provider": "DeepSeek", "model": "m", "api_key": "k"}, _tpl_config())
    prompt = engine.build_prompt("病历正文")
    assert "姓名" in prompt and "年龄" in prompt and "病历正文" in prompt


def test_parse_response_strips_json_fence():
    parsed = MedicalExtractionEngine.parse_response('```json\n{"姓名": "张三"}\n```')
    assert parsed == {"姓名": "张三"}


def test_parse_response_invalid_raises():
    with pytest.raises(RuntimeError):
        MedicalExtractionEngine.parse_response("not json at all")


def test_validate_data_types_and_defaults():
    engine = MedicalExtractionEngine({"provider": "DeepSeek", "model": "m", "api_key": "k"}, _tpl_config())
    # 年龄给字符串数字 -> 转 int；姓名缺失 -> "-1"
    validated = engine.validate_data({"年龄": "36"})
    assert validated["年龄"] == 36
    assert validated["姓名"] == "-1"
    # 年龄缺失 -> -1（整数）
    assert engine.validate_data({"姓名": "李四"})["年龄"] == -1


def test_extract_end_to_end_mocked():
    engine = MedicalExtractionEngine({"provider": "DeepSeek", "model": "m", "api_key": "k"}, _tpl_config())
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {"choices": [{"message": {"content": '{"姓名": "王五", "年龄": "40"}'}}]}
    with patch("mee.modules.medical_extractor.engine.requests.post", return_value=fake_resp):
        row = engine.extract("一段合成病历", source="王五.md")
    assert row["姓名"] == "王五"
    assert row["年龄"] == 40
    assert row["_source"] == "王五.md"
    assert row["_status"] == "success"


def test_load_template_config_from_xlsx(fixtures_dir):
    cfg = load_template_config(str(fixtures_dir / "template.xlsx"))
    columns = [f["column"] for f in cfg["fields"]]
    assert "姓名" in columns and "住院号" in columns


def test_load_template_config_from_json(fixtures_dir):
    cfg = load_template_config(str(fixtures_dir / "template_config.json"))
    assert cfg["fields"]
    assert any(f["column"] == "主诉" for f in cfg["fields"])
