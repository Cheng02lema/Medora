"""项目 CRUD + 配置 + 病人导入 API。"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..state import project_store
from ..project import Project, DEFAULT_OCR_CONFIG, DEFAULT_LLM_CONFIG, DEFAULT_PREPROCESS_CONFIG
from ..ws import manager

router = APIRouter(prefix="/projects", tags=["projects"])


# ============ 项目 CRUD ============

@router.get("")
def list_projects():
    return [p.to_summary() for p in project_store.all()]


class CreateProjectRequest(BaseModel):
    name: str
    source_type: str = "image"  # "image" | "excel" | "text"


@router.post("")
def create_project(req: CreateProjectRequest):
    project = project_store.create(req.name, req.source_type)
    return project.to_summary()


@router.get("/{project_id}")
def get_project(project_id: str):
    p = project_store.get(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    return p.to_detail()


@router.delete("/{project_id}")
def delete_project(project_id: str):
    if not project_store.get(project_id):
        raise HTTPException(404, "项目不存在")
    project_store.remove(project_id, delete_files=True)
    return {"ok": True}


class RenameProjectRequest(BaseModel):
    name: str


@router.patch("/{project_id}")
def rename_project(project_id: str, req: RenameProjectRequest):
    p = project_store.get(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    name = (req.name or "").strip()
    if not name:
        raise HTTPException(400, "名称不能为空")
    project_store.rename(project_id, name)
    p = project_store.get(project_id)
    return p.to_summary() if p else {"ok": True, "name": name}


# ============ 项目配置 ============

@router.get("/{project_id}/config")
def get_config(project_id: str):
    """返回项目配置 + 全局默认 + effective（合并结果）。"""
    p = project_store.get(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    from ..state import config as global_config
    from ..config_resolve import effective_ocr, effective_llm, global_ocr_dict, global_llm_dict

    eff_ocr = effective_ocr(p, global_config)
    eff_llm = effective_llm(p, global_config)
    return {
        "ocr_use_global": bool(getattr(p, "ocr_use_global", True)),
        "llm_use_global": bool(getattr(p, "llm_use_global", True)),
        "ocr_override": dict(p.ocr_config or {}),
        "llm_override": dict(p.llm_config or {}),
        "global_ocr": {
            **global_ocr_dict(global_config),
            "token_configured": bool(global_config.get_secret("ocr_api")),
        },
        "global_llm": {
            **global_llm_dict(global_config),
            "api_key_configured": bool(global_config.get_secret("extract_llm")),
        },
        "ocr": eff_ocr,
        "llm": eff_llm,
        "preprocess": p.preprocess_config,
        "slice_regions": p.slice_regions,
        "pipeline": {
            "extraction_template": p.extraction_template,
            "output_excel": p.output_excel,
            "make_docx": p.make_docx,
        },
    }


class UpdateOCRConfigRequest(BaseModel):
    """use_global=True 时清空项目覆盖；False 时写入 url/model/preset/custom_params。
    Token 请在全局设置中配置，这里忽略 token 字段。"""
    use_global: Optional[bool] = None
    url: Optional[str] = None
    model: Optional[str] = None
    preset: Optional[str] = None
    custom_params: Optional[Dict[str, Any]] = None


@router.put("/{project_id}/config/ocr")
def update_ocr_config(project_id: str, req: UpdateOCRConfigRequest):
    p = project_store.get(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")

    if req.use_global is True:
        p.ocr_use_global = True
        p.ocr_config = {}
        p.save()
        return {"ok": True, "ocr_use_global": True}

    if req.use_global is False or req.use_global is None:
        # 有字段更新时视为进入覆盖模式
        has_fields = any(x is not None for x in (req.url, req.model, req.preset, req.custom_params))
        if req.use_global is False or has_fields:
            p.ocr_use_global = False
            cfg = dict(p.ocr_config or {})
            if req.url is not None:
                cfg["url"] = req.url
            if req.model is not None:
                cfg["model"] = req.model
            if req.preset is not None:
                cfg["preset"] = req.preset
            if req.custom_params is not None:
                from antigravity.engine.ocr_presets import _normalize_params
                cfg["custom_params"] = _normalize_params(req.custom_params)
            p.ocr_config = cfg
    p.save()
    return {"ok": True, "ocr_use_global": p.ocr_use_global}


class UpdateLLMConfigRequest(BaseModel):
    use_global: Optional[bool] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    base_url: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


@router.put("/{project_id}/config/llm")
def update_llm_config(project_id: str, req: UpdateLLMConfigRequest):
    p = project_store.get(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")

    if req.use_global is True:
        p.llm_use_global = True
        p.llm_config = {}
        p.save()
        return {"ok": True, "llm_use_global": True}

    has_fields = any(
        x is not None
        for x in (req.provider, req.model, req.base_url, req.temperature, req.max_tokens)
    )
    if req.use_global is False or has_fields:
        p.llm_use_global = False
        cfg = dict(p.llm_config or {})
        if req.provider is not None:
            cfg["provider"] = req.provider
        if req.model is not None:
            cfg["model"] = req.model
        if req.base_url is not None:
            cfg["base_url"] = req.base_url
        if req.temperature is not None:
            cfg["temperature"] = req.temperature
        if req.max_tokens is not None:
            cfg["max_tokens"] = req.max_tokens
        p.llm_config = cfg
    p.save()
    return {"ok": True, "llm_use_global": p.llm_use_global}


class UpdatePreprocessConfigRequest(BaseModel):
    preset: Optional[str] = None
    ops: Optional[List[Dict]] = None
    mask_regions: Optional[List[Dict]] = None
    roi_regions: Optional[List[Dict]] = None
    collect_metrics: Optional[bool] = None
    # 兼容旧字段
    contrast: Optional[float] = None
    sharpness: Optional[float] = None
    brightness: Optional[float] = None
    denoise: Optional[bool] = None
    binarize: Optional[bool] = None
    binarize_threshold: Optional[int] = None


@router.put("/{project_id}/config/preprocess")
def update_preprocess_config(project_id: str, req: UpdatePreprocessConfigRequest):
    p = project_store.get(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    for k, v in req.dict(exclude_none=True).items():
        p.preprocess_config[k] = v
    p.save()
    return {"ok": True}


class UpdatePipelineConfigRequest(BaseModel):
    extraction_template: Optional[str] = None
    output_excel: Optional[str] = None
    make_docx: Optional[bool] = None


@router.put("/{project_id}/config/pipeline")
def update_pipeline_config(project_id: str, req: UpdatePipelineConfigRequest):
    p = project_store.get(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    if req.extraction_template is not None:
        p.extraction_template = req.extraction_template
    if req.output_excel is not None:
        p.output_excel = req.output_excel
    if req.make_docx is not None:
        p.make_docx = req.make_docx
    p.save()
    return {"ok": True}


class UpdateSliceRegionsRequest(BaseModel):
    regions: List[Dict]


@router.put("/{project_id}/config/slice-regions")
def update_slice_regions(project_id: str, req: UpdateSliceRegionsRequest):
    p = project_store.get(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    p.slice_regions = req.regions
    p.save()
    return {"ok": True}


# ============ 病人导入 ============

class ImportFolderRequest(BaseModel):
    path: str


@router.post("/{project_id}/patients/import-folder")
def import_patients_folder(project_id: str, req: ImportFolderRequest):
    """从图片文件夹导入病人。"""
    p = project_store.get(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    added = p.import_image_folder(req.path)
    if not added:
        raise HTTPException(400, "目录不存在或未找到含图片的病人文件夹")
    for pat in added:
        manager.emit_patient_update(pat.to_summary())
    return [pat.to_summary() for pat in added]


class ImportTextRequest(BaseModel):
    path: str


@router.post("/{project_id}/patients/import-text")
def import_patients_text(project_id: str, req: ImportTextRequest):
    """从文本文件文件夹导入(MD/DOCX/TXT)。"""
    p = project_store.get(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    added = p.import_text_files(req.path)
    if not added:
        raise HTTPException(400, "目录不存在或未找到文本文件")
    for pat in added:
        manager.emit_patient_update(pat.to_summary())
    return [pat.to_summary() for pat in added]


class ImportExcelRequest(BaseModel):
    path: str
    text_columns: str = ""  # 逗号分隔的列名,空则自动


@router.post("/{project_id}/patients/import-excel")
def import_patients_excel(project_id: str, req: ImportExcelRequest):
    """从 Excel 拆分:每行=1病人。"""
    p = project_store.get(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    added = p.import_excel_rows(req.path, req.text_columns)
    if not added:
        raise HTTPException(400, "Excel 文件无有效数据行")
    for pat in added:
        manager.emit_patient_update(pat.to_summary())
    return [pat.to_summary() for pat in added]


# ============ 项目内病人列表 ============

@router.get("/{project_id}/patients")
def list_project_patients(project_id: str):
    """获取项目内所有病人。"""
    p = project_store.get(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    return [pat.to_summary() for pat in p.patient_store.all()]
