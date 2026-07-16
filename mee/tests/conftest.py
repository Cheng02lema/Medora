"""pytest 公共夹具：内存 keyring 后端 + 合成数据路径。"""

from __future__ import annotations

from pathlib import Path

import pytest


FIXTURES = Path(__file__).resolve().parent / "fixtures"


class InMemoryKeyring:
    """一个极简的内存 keyring 后端，避免测试触碰真实系统钥匙串。"""

    def __init__(self):
        self.store = {}

    def set_password(self, service, name, value):
        self.store[(service, name)] = value

    def get_password(self, service, name):
        return self.store.get((service, name))

    def delete_password(self, service, name):
        self.store.pop((service, name), None)


@pytest.fixture
def memory_keyring(monkeypatch):
    """把 mee.core.secrets 的 keyring 后端替换为内存实现。"""
    import keyring

    from mee.core import secrets

    backend = InMemoryKeyring()
    monkeypatch.setattr(keyring, "get_keyring", lambda: backend)
    monkeypatch.setattr(keyring, "set_password", backend.set_password)
    monkeypatch.setattr(keyring, "get_password", backend.get_password)
    monkeypatch.setattr(keyring, "delete_password", backend.delete_password)
    secrets.LAST_BACKEND_AVAILABLE = True
    return backend


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture(scope="session")
def qapp():
    """提供一个进程级 QApplication，供 QThread/QObject 子类实例化。"""
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    return app


@pytest.fixture(autouse=True)
def _ensure_qapp(request):
    """需要 Qt 的测试自动获得 QApplication。"""
    if "no_qapp" in request.keywords:
        return
    request.getfixturevalue("qapp")
