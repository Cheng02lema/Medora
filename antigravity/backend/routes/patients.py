"""病人 CRUD：导入文件夹、列表、详情、删除。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..state import store, find_patient

router = APIRouter(prefix="/patients", tags=["patients"])


class ImportRequest(BaseModel):
    path: str


@router.get("")
def list_patients():
    return [p.to_summary() for p in store.all()]


@router.post("/import")
def import_patients(req: ImportRequest):
    added = store.import_parent(req.path)
    if not added:
        single = store.add_folder(req.path)
        added = [single] if single else []
    if not added:
        raise HTTPException(400, detail="目录不存在或未找到含图片的病人文件夹")
    return [p.to_summary() for p in added]


@router.get("/{patient_id}")
def get_patient(patient_id: str):
    p, _ = find_patient(patient_id)
    if not p:
        raise HTTPException(404, detail="病人不存在")
    return p.to_detail()


@router.get("/{patient_id}/detail")
def get_detail(patient_id: str):
    p, _ = find_patient(patient_id)
    if not p:
        raise HTTPException(404, detail="病人不存在")
    return p.to_detail()


@router.delete("/{patient_id}")
def delete_patient(patient_id: str):
    p, project = find_patient(patient_id)
    if not p:
        raise HTTPException(404, detail="病人不存在")
    if project is not None:
        project.patient_store.remove(patient_id, delete_files=True)
    else:
        store.remove(patient_id, delete_files=True)
    return {"ok": True}


class RenameRequest(BaseModel):
    name: str


@router.patch("/{patient_id}")
def rename_patient(patient_id: str, req: RenameRequest):
    p, project = find_patient(patient_id)
    if not p:
        raise HTTPException(404, detail="病人不存在")
    name = (req.name or "").strip()
    if not name:
        raise HTTPException(400, detail="名称不能为空")
    if project is not None:
        project.patient_store.rename(patient_id, name)
    else:
        store.rename(patient_id, name)
    p, _ = find_patient(patient_id)
    return p.to_summary() if p else {"ok": True, "name": name}
