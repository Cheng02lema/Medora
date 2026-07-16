"""FastAPI 端到端测试：导入病人 → 触发提取（mock 后端）→ 断言状态与导出。

用独立的 PatientStore/ConfigManager 实例替换 backend.state 里的单例，
避免测试污染真实的 workspace/keyring。
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    from antigravity.backend import patient as patient_module
    from antigravity.backend import state as state_module

    # 隔离的 store + config，避免污染真实数据
    isolated_store = patient_module.PatientStore(tmp_path / "workspace")
    monkeypatch.setattr(state_module, "store", isolated_store)

    from antigravity.engine.config_manager import ConfigManager
    isolated_config = ConfigManager(filepath=tmp_path / "settings.json")
    monkeypatch.setattr(state_module, "config", isolated_config)

    # routes 模块里是 `from ..state import store` 的引用拷贝，需要一并替换
    from antigravity.backend.routes import patients as patients_routes
    from antigravity.backend.routes import settings as settings_routes
    from antigravity.backend.routes import tasks as tasks_routes
    from antigravity.backend.routes import files as files_routes

    monkeypatch.setattr(patients_routes, "store", isolated_store)
    monkeypatch.setattr(files_routes, "store", isolated_store)
    monkeypatch.setattr(settings_routes, "config", isolated_config)
    monkeypatch.setattr(tasks_routes, "store", isolated_store)
    monkeypatch.setattr(tasks_routes, "config", isolated_config)
    tasks_routes._task_summaries.clear()

    from antigravity.backend.app import app
    with TestClient(app) as c:
        yield c


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_import_and_list_patients(client, sample_parent):
    resp = client.post("/patients/import", json={"path": str(sample_parent)})
    assert resp.status_code == 200
    added = resp.json()
    assert sorted(p["name"] for p in added) == ["张三", "李四"]
    assert all(p["status"] == "pending" for p in added)

    listing = client.get("/patients").json()
    assert len(listing) == 2


def test_import_missing_path_404(client):
    resp = client.post("/patients/import", json={"path": "/nonexistent/xyz"})
    assert resp.status_code == 400


def test_patient_detail(client, sample_parent):
    added = client.post("/patients/import", json={"path": str(sample_parent)}).json()
    pid = added[0]["id"]
    detail = client.get(f"/patients/{pid}/detail").json()
    assert len(detail["thumbnails"]) == 2
    assert detail["merged_text"] is None


def test_settings_roundtrip(client):
    client.put("/settings/ocr", json={"url": "http://ocr.example", "token": "sk-1"})
    client.put("/settings/extract_llm", json={"provider": "DeepSeek", "api_key": "sk-2"})
    client.put("/settings/pipeline", json={"extraction_template": "/tmp/t.json"})

    settings = client.get("/settings").json()
    assert settings["ocr"]["url"] == "http://ocr.example"
    assert settings["ocr"]["token_configured"] is True
    assert settings["extract_llm"]["api_key_configured"] is True
    assert settings["pipeline"]["extraction_template"] == "/tmp/t.json"


def test_extract_task_end_to_end(client, sample_parent, excel_template, tmp_path):
    added = client.post("/patients/import", json={"path": str(sample_parent)}).json()
    pids = [p["id"] for p in added]

    out = tmp_path / "结果.xlsx"
    client.put("/settings/ocr", json={"url": "http://x", "model": "m", "token": "tok"})
    client.put("/settings/extract_llm", json={"provider": "DeepSeek", "model": "m", "api_key": "k"})
    client.put("/settings/pipeline", json={
        "extraction_template": str(excel_template),
        "output_excel": str(out),
        "enable_preprocess": False,
    })

    fake_ocr = MagicMock()
    fake_ocr.process_file.return_value = [
        {"layoutParsingResults": [{"markdown": {"text": "合成文本", "images": {}}, "outputImages": {}}]}
    ]
    fake_engine = MagicMock()
    fake_engine.extract.side_effect = lambda content, source="": {
        "姓名": source, "住院号": f"ID-{source}", "_source": source, "_status": "success"}

    with patch("antigravity.engine.ocr_client.AsyncOCRClient", return_value=fake_ocr), \
         patch("antigravity.engine.medical_extractor.engine.MedicalExtractionEngine", return_value=fake_engine):
        resp = client.post("/tasks/extract", json={"patient_ids": pids})
        assert resp.status_code == 200
        task_id = resp.json()["task_id"]

        # 任务在线程池异步跑，轮询等待完成（测试环境很快）
        deadline = time.time() + 5
        summary = None
        while time.time() < deadline:
            r = client.get(f"/tasks/{task_id}").json()
            if r.get("status") != "running":
                summary = r
                break
            time.sleep(0.05)

    assert summary is not None
    assert summary["done"] == 2
    assert summary["error"] == 0
    assert out.exists()

    listing = client.get("/patients").json()
    assert all(p["status"] == "done" for p in listing)
    assert all(p["row"]["姓名"] == p["name"] for p in listing)


def test_extract_missing_patient_404(client):
    resp = client.post("/tasks/extract", json={"patient_ids": ["nope"]})
    assert resp.status_code == 404


def test_delete_patient(client, sample_parent):
    added = client.post("/patients/import", json={"path": str(sample_parent)}).json()
    pid = added[0]["id"]
    assert client.delete(f"/patients/{pid}").status_code == 200
    assert client.get(f"/patients/{pid}/detail").status_code == 404
