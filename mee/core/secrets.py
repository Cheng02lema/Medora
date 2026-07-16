"""集中管理敏感信息（OCR token / LLM API key）。

优先使用系统 keyring（macOS 钥匙串 / Windows 凭据管理器 / Linux Secret
Service）保存密钥，配置文件中只保留形如 ``keyring:mee/<name>`` 的引用。
当 keyring 不可用（没有后端、无桌面会话等）时回落到明文，并置位
``LAST_BACKEND_AVAILABLE`` 供 UI 给出警告。
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

SERVICE_NAME = "mee"
REF_PREFIX = "keyring:"

# 记录最近一次访问 keyring 是否成功，UI 可据此提示用户密钥未被安全存储。
LAST_BACKEND_AVAILABLE = True


def _get_keyring():
    """惰性导入 keyring，并探测是否存在可用后端。返回模块或 None。"""
    global LAST_BACKEND_AVAILABLE
    try:
        import keyring
        from keyring.errors import NoKeyringError  # noqa: F401
    except Exception as exc:  # keyring 未安装
        logger.warning("keyring 不可用（导入失败）：%s", exc)
        LAST_BACKEND_AVAILABLE = False
        return None

    try:
        backend = keyring.get_keyring()
        # keyring 的 fail backend 在没有可用系统后端时会被选中，标记名含 "fail"
        backend_name = type(backend).__module__ + "." + type(backend).__name__
        if "fail" in backend_name.lower():
            logger.warning("keyring 无可用后端：%s", backend_name)
            LAST_BACKEND_AVAILABLE = False
            return None
    except Exception as exc:
        logger.warning("keyring 后端探测失败：%s", exc)
        LAST_BACKEND_AVAILABLE = False
        return None

    LAST_BACKEND_AVAILABLE = True
    return keyring


def make_ref(name: str) -> str:
    """构造一个 keyring 引用字符串。"""
    return f"{REF_PREFIX}{SERVICE_NAME}/{name}"


def is_ref(value: Optional[str]) -> bool:
    return bool(value) and value.startswith(REF_PREFIX)


def _parse_ref(ref: str) -> str:
    """从 ``keyring:mee/<name>`` 取出 <name>。"""
    body = ref[len(REF_PREFIX):]
    if "/" in body:
        _, name = body.split("/", 1)
        return name
    return body


def set_secret(name: str, value: str) -> str:
    """把密钥写入 keyring，返回可存进配置文件的引用字符串。

    keyring 不可用时返回明文本身（调用方应据 ``LAST_BACKEND_AVAILABLE``
    决定是否警告）。空值直接返回空串。
    """
    if not value:
        return ""
    kr = _get_keyring()
    if kr is None:
        return value
    try:
        kr.set_password(SERVICE_NAME, name, value)
        return make_ref(name)
    except Exception as exc:
        logger.warning("写入 keyring 失败（%s），回落明文：%s", name, exc)
        global LAST_BACKEND_AVAILABLE
        LAST_BACKEND_AVAILABLE = False
        return value


def resolve(ref_or_value: Optional[str]) -> str:
    """把配置里的引用（或明文）解析为真实密钥。"""
    if not ref_or_value:
        return ""
    if not is_ref(ref_or_value):
        # 明文，直接返回
        return ref_or_value
    name = _parse_ref(ref_or_value)
    kr = _get_keyring()
    if kr is None:
        logger.warning("无法解析 keyring 引用（后端不可用）：%s", ref_or_value)
        return ""
    try:
        secret = kr.get_password(SERVICE_NAME, name)
        return secret or ""
    except Exception as exc:
        logger.warning("读取 keyring 失败（%s）：%s", name, exc)
        return ""


def delete_secret(name: str) -> None:
    kr = _get_keyring()
    if kr is None:
        return
    try:
        kr.delete_password(SERVICE_NAME, name)
    except Exception:
        pass
