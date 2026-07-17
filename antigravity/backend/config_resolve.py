"""全局默认 + 项目覆盖 的 effective 配置解析。

约定：
- 密钥（OCR Token / LLM Key）仅全局
- 用户 OCR 预设库仅全局
- 抽取模板 / 导出路径 / 提示词 仅项目
- OCR / LLM 运行参数：项目 use_global=True 时全用全局；False 时用项目覆盖（空字段仍可回落全局）
- 批量并发：全局默认；项目可覆盖 max_parallel_patients
"""

from __future__ import annotations

from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .project import Project

# 对外「同时处理」硬上限，防打爆 OCR/LLM
MAX_PARALLEL_PATIENTS_CAP = 4


def clamp_parallel_patients(value: Any, default: int = 1) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = default
    if n < 1:
        n = 1
    if n > MAX_PARALLEL_PATIENTS_CAP:
        n = MAX_PARALLEL_PATIENTS_CAP
    return n


def global_max_parallel_patients(config) -> int:
    exe = config.data.get("execution", {}) or {}
    return clamp_parallel_patients(exe.get("max_parallel_patients", 1), 1)


def effective_max_parallel_patients(project: Optional["Project"], config) -> int:
    """项目覆盖 > 全局默认；始终 clamp 到 1..CAP。"""
    g = global_max_parallel_patients(config)
    if project is None or getattr(project, "execution_use_global", True):
        return g
    raw = getattr(project, "max_parallel_patients", None)
    if raw is None:
        return g
    return clamp_parallel_patients(raw, g)


def global_ocr_dict(config) -> Dict[str, Any]:
    ocr = config.data.get("ocr_api", {}) or {}
    return {
        "url": ocr.get("url", ""),
        "model": ocr.get("model", "") or "PaddleOCR-VL-1.5",
        "preset": ocr.get("preset", "") or "paper_photo",
        "custom_params": dict(ocr.get("custom_params") or {}),
        "user_presets": list(ocr.get("user_presets") or []),
    }


def global_llm_dict(config) -> Dict[str, Any]:
    llm = config.data.get("extract_llm", {}) or {}
    return {
        "provider": llm.get("provider", "") or "DeepSeek",
        "model": llm.get("model", ""),
        "base_url": llm.get("base_url", ""),
        "temperature": llm.get("temperature", 0.0),
        "max_tokens": llm.get("max_tokens", 8000),
    }


def _pick(override: Dict[str, Any], key: str, fallback: Any) -> Any:
    if key not in override:
        return fallback
    val = override.get(key)
    if val is None:
        return fallback
    if isinstance(val, str) and val.strip() == "" and not isinstance(fallback, str):
        return fallback
    # 空字符串对 url/model 允许回落
    if isinstance(val, str) and val.strip() == "" and key in ("url", "model", "base_url", "provider", "preset"):
        return fallback
    return val


def effective_ocr(project: Optional["Project"], config) -> Dict[str, Any]:
    g = global_ocr_dict(config)
    if project is None or getattr(project, "ocr_use_global", True):
        return {
            **g,
            "use_global": True,
            "token_configured": bool(config.get_secret("ocr_api")),
        }
    o = project.ocr_config or {}
    return {
        "url": _pick(o, "url", g["url"]),
        "model": _pick(o, "model", g["model"]),
        "preset": _pick(o, "preset", g["preset"]),
        "custom_params": o["custom_params"] if "custom_params" in o and o["custom_params"] is not None else g["custom_params"],
        "user_presets": g["user_presets"],
        "use_global": False,
        "token_configured": bool(config.get_secret("ocr_api")),
    }


def effective_llm(project: Optional["Project"], config) -> Dict[str, Any]:
    g = global_llm_dict(config)
    if project is None or getattr(project, "llm_use_global", True):
        return {
            **g,
            "use_global": True,
            "api_key_configured": bool(config.get_secret("extract_llm")),
        }
    o = project.llm_config or {}
    return {
        "provider": _pick(o, "provider", g["provider"]),
        "model": _pick(o, "model", g["model"]),
        "base_url": _pick(o, "base_url", g["base_url"]),
        "temperature": o["temperature"] if "temperature" in o and o["temperature"] is not None else g["temperature"],
        "max_tokens": o["max_tokens"] if "max_tokens" in o and o["max_tokens"] is not None else g["max_tokens"],
        "use_global": False,
        "api_key_configured": bool(config.get_secret("extract_llm")),
    }


def runner_settings_for_patient(patient, project: Optional["Project"], config) -> Dict[str, Any]:
    """供 StageRunner 使用的合并配置。"""
    ocr = effective_ocr(project, config)
    llm = effective_llm(project, config)
    pre = {}
    if project is not None:
        pre = project.preprocess_config or {}

    pipeline_global = config.data.get("pipeline", {}) or {}
    extraction_template = ""
    output_excel = ""
    make_docx = False
    prompt_md = ""
    slice_regions = []

    if project is not None:
        extraction_template = project.extraction_template or ""
        output_excel = project.output_excel or ""
        make_docx = bool(project.make_docx)
        prompt_md = project.prompt_engineered_md or ""
        slice_regions = project.slice_regions or []
    else:
        extraction_template = pipeline_global.get("extraction_template", "")
        output_excel = pipeline_global.get("output_excel", "")
        make_docx = bool(pipeline_global.get("make_docx", False))

    return {
        "ocr_url": ocr.get("url", ""),
        "ocr_model": ocr.get("model", ""),
        "ocr_preset": ocr.get("preset", "paper_photo"),
        "ocr_custom_params": ocr.get("custom_params") or {},
        "ocr_user_presets": ocr.get("user_presets") or [],
        "ocr_token": config.get_secret("ocr_api"),
        "extraction_template": extraction_template,
        "output_excel": output_excel,
        "extract_llm": {
            "provider": llm.get("provider", "DeepSeek"),
            "model": llm.get("model", ""),
            "api_url": llm.get("base_url", ""),
            "api_key": config.get_secret("extract_llm"),
            "temperature": llm.get("temperature", 0.0),
            "max_tokens": llm.get("max_tokens", 8000),
        },
        "make_docx": make_docx,
        "preprocess_config": pre,
        "mask_regions": pre.get("mask_regions", []) if isinstance(pre, dict) else [],
        "slice_regions": slice_regions,
        "cleanup_pattern": "*右表格_0.md",
        "prompt_md_path": prompt_md,
        "max_parallel_patients": effective_max_parallel_patients(project, config),
    }
