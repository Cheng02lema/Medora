"""病人图片的静态资源访问（源图 / 预处理 / 切片 / 缩略图）。"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..state import find_patient
from ..patient import IMAGE_EXTS

router = APIRouter(prefix="/files", tags=["files"])


@router.get("/image/{patient_id}/{stage}/{filename:path}")
def get_image(patient_id: str, stage: str, filename: str):
    """获取原图（源图/预处理/切片）。"""
    p, _ = find_patient(patient_id)
    if not p:
        raise HTTPException(404, detail="病人不存在")

    if stage == "source":
        base = Path(p.source_dir)
    elif stage == "preprocess":
        base = p.preprocess_dir
    elif stage == "preprocess_preview":
        base = Path(p.work_dir) / "preprocess_preview"
    elif stage == "preprocess_bench":
        base = Path(p.work_dir) / "preprocess_bench"
    elif stage == "slice":
        base = p.slice_dir
    elif stage == "ocr":
        # OCR 目录下的 md 等文件
        base = p.ocr_dir
    else:
        raise HTTPException(400, detail=f"不支持的阶段：{stage}")

    target = (base / filename).resolve()
    base_resolved = base.resolve()
    if base_resolved not in target.parents and target != base_resolved:
        raise HTTPException(400, detail="非法路径")
    if not target.is_file():
        raise HTTPException(404, detail="文件不存在")
    return FileResponse(str(target))


@router.get("/thumb/{patient_id}/{stage}/{filename:path}")
def get_thumb(patient_id: str, stage: str, filename: str):
    """获取缩略图（目前直接返回原图，后续可加 PIL 缩放）。"""
    return get_image(patient_id, stage, filename)
