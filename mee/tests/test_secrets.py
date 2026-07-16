"""secrets 模块与配置密钥迁移测试（使用内存 keyring）。"""

from __future__ import annotations

import json

from mee.core import secrets


def test_set_and_resolve_roundtrip(memory_keyring):
    ref = secrets.set_secret("ocr_token", "sk-abc123")
    assert secrets.is_ref(ref)
    assert ref == "keyring:mee/ocr_token"
    assert secrets.resolve(ref) == "sk-abc123"


def test_resolve_plaintext_passthrough(memory_keyring):
    # 非引用值原样返回（兼容旧明文配置）
    assert secrets.resolve("plain-token") == "plain-token"


def test_set_empty_returns_empty(memory_keyring):
    assert secrets.set_secret("ocr_token", "") == ""
    assert secrets.resolve("") == ""


def test_config_migrates_plaintext_token(tmp_path, memory_keyring):
    from mee.config.manager import ConfigManager

    # 造一个带明文 token 的旧配置
    cfg_file = tmp_path / "settings.json"
    legacy = {
        "ocr_api": {"url": "http://x", "token": "sk-legacy", "model": "m", "preset": "original"},
        "extract_llm": {"provider": "DeepSeek", "api_key": "sk-extract"},
    }
    cfg_file.write_text(json.dumps(legacy), encoding="utf-8")

    mgr = ConfigManager(filepath=cfg_file)

    # 明文不应再出现在配置里
    saved = json.loads(cfg_file.read_text(encoding="utf-8"))
    assert "token" not in saved["ocr_api"]
    assert "api_key" not in saved["extract_llm"]
    assert secrets.is_ref(saved["ocr_api"]["token_ref"])
    assert secrets.is_ref(saved["extract_llm"]["api_key_ref"])

    # 通过 get_secret 能解析回明文
    assert mgr.get_secret("ocr_api") == "sk-legacy"
    assert mgr.get_secret("extract_llm") == "sk-extract"


def test_config_set_secret_stores_ref(tmp_path, memory_keyring):
    from mee.config.manager import ConfigManager

    cfg_file = tmp_path / "settings.json"
    mgr = ConfigManager(filepath=cfg_file)
    mgr.set_secret("prompt_llm", "sk-prompt")

    saved = json.loads(cfg_file.read_text(encoding="utf-8"))
    assert secrets.is_ref(saved["prompt_llm"]["api_key_ref"])
    assert mgr.get_secret("prompt_llm") == "sk-prompt"
