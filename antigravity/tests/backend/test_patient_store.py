"""病人发现、导入去重、持久化、恢复测试。"""

from __future__ import annotations

from antigravity.backend.patient import PatientStore


def test_import_parent_discovers_patients(sample_parent, workspace):
    store = PatientStore(workspace)
    added = store.import_parent(str(sample_parent))
    names = sorted(p.name for p in added)
    assert names == ["张三", "李四"]
    assert all(p.status == "pending" for p in added)


def test_import_parent_skips_empty_dirs(tmp_path, workspace):
    from PIL import Image

    parent = tmp_path / "病历"
    (parent / "有图").mkdir(parents=True)
    Image.new("RGB", (10, 10), (0, 0, 0)).save(parent / "有图" / "a.jpg")
    (parent / "空目录").mkdir()
    store = PatientStore(workspace)
    added = store.import_parent(str(parent))
    assert [p.name for p in added] == ["有图"]


def test_add_folder_dedup_by_source(sample_parent, workspace):
    store = PatientStore(workspace)
    p1 = store.add_folder(str(sample_parent / "张三"))
    p2 = store.add_folder(str(sample_parent / "张三"))
    assert p1.id == p2.id
    assert len(store.all()) == 1


def test_state_persist_and_reload(sample_parent, workspace):
    store = PatientStore(workspace)
    store.import_parent(str(sample_parent))
    zhang = next(p for p in store.all() if p.name == "张三")
    zhang.status = "done"
    zhang.row = {"姓名": "张三", "_status": "success"}
    zhang.save()

    store2 = PatientStore(workspace)
    store2.load()
    restored = store2.get(zhang.id)
    assert restored is not None
    assert restored.status == "done"
    assert restored.row["姓名"] == "张三"


def test_detail_view_includes_thumbnails(sample_parent, workspace):
    store = PatientStore(workspace)
    added = store.import_parent(str(sample_parent))
    zhang = next(p for p in added if p.name == "张三")
    detail = zhang.to_detail()
    assert len(detail["thumbnails"]) == 2
    assert detail["status"] == "pending"
    assert detail["ocr_texts"] == []


def test_summary_hides_internal_paths(sample_parent, workspace):
    store = PatientStore(workspace)
    added = store.import_parent(str(sample_parent))
    summary = added[0].to_summary()
    assert "work_dir" not in summary
    assert "source_dir" not in summary
    assert set(summary.keys()) == {"id", "name", "status", "row", "error_message"}
