"""OCR/大模型/流程配置的读写。密钥经 keyring（ConfigManager.get_secret/set_secret），
接口只回传是否已配置（masked），不回传明文。包含测试连接端点。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..state import config

router = APIRouter(prefix="/settings", tags=["settings"])


def _user_presets() -> List[Dict[str, Any]]:
    ocr = config.data.get("ocr_api", {}) or {}
    raw = ocr.get("user_presets") or []
    return list(raw) if isinstance(raw, list) else []


def _save_user_presets(presets: List[Dict[str, Any]]) -> None:
    config.update_section("ocr_api", {"user_presets": presets})


def _slug_key(label: str) -> str:
    """生成稳定英文 key；中文名则用 user_ 前缀 + 短 hash。"""
    import hashlib
    raw = (label or "").strip()
    ascii_part = re.sub(r"[^a-zA-Z0-9]+", "_", raw).strip("_").lower()
    if ascii_part and re.match(r"^[a-z]", ascii_part):
        key = ascii_part[:32]
    else:
        h = hashlib.md5(raw.encode("utf-8")).hexdigest()[:8]
        key = f"user_{h}"
    existing = {p.get("key") for p in _user_presets()}
    from antigravity.engine.ocr_presets import OCR_PRESET_MAP
    existing |= set(OCR_PRESET_MAP.keys())
    if key not in existing:
        return key
    i = 2
    while f"{key}_{i}" in existing:
        i += 1
    return f"{key}_{i}"


# ============ 读取 ============

@router.get("")
def get_settings():
    """全局默认配置（账号 + 默认策略）。模板请在项目设置中配置。"""
    ocr = config.data.get("ocr_api", {})
    extract = config.data.get("extract_llm", {})
    agent = config.data.get("agent_llm", {})
    return {
        "ocr": {
            "url": ocr.get("url", ""),
            "model": ocr.get("model", ""),
            "preset": ocr.get("preset", "paper_photo"),
            "custom_params": ocr.get("custom_params") or {},
            "user_presets": _user_presets(),
            "token_configured": bool(config.get_secret("ocr_api")),
        },
        "extract_llm": {
            "provider": extract.get("provider", "DeepSeek"),
            "model": extract.get("model", ""),
            "base_url": extract.get("base_url", ""),
            "api_key_configured": bool(config.get_secret("extract_llm")),
            "temperature": extract.get("temperature", 0.0),
            "max_tokens": extract.get("max_tokens", 8000),
        },
        "agent_llm": {
            "provider": agent.get("provider", "DeepSeek"),
            "model": agent.get("model", ""),
            "base_url": agent.get("base_url", ""),
            "api_key_configured": bool(config.get_secret("agent_llm")),
            "temperature": agent.get("temperature", 0.2),
            "max_tokens": agent.get("max_tokens", 2000),
        },
        # 兼容旧前端：pipeline 字段保留但 UI 不再编辑模板
        "pipeline": {
            "extraction_template": "",
            "output_excel": "",
            "make_docx": False,
        },
    }


# ============ OCR 预设列表（内置 + 用户） ============

@router.get("/ocr/presets")
def get_ocr_presets():
    """返回内置 + 用户自定义预设（含展开后的 params）。"""
    from antigravity.engine.ocr_presets import list_presets, OCR_MODELS
    return {
        "presets": list_presets(_user_presets()),
        "models": OCR_MODELS,
    }


# ============ OCR 参数 schema ============

@router.get("/ocr/params")
def get_ocr_param_schema():
    """返回所有可配置的 OCR 参数 schema。"""
    from antigravity.engine.ocr_presets import OCR_PARAM_SCHEMA, BASE_OPTIONAL_PAYLOAD
    return {"params": OCR_PARAM_SCHEMA, "defaults": BASE_OPTIONAL_PAYLOAD}


# ============ 预设展开 ============

@router.get("/ocr/preset/{preset_key}")
def get_preset_details(preset_key: str):
    """返回某个预设的实际参数值。"""
    from antigravity.engine.ocr_presets import resolve_preset_params
    payload = resolve_preset_params(preset_key, _user_presets())
    if payload is None:
        raise HTTPException(404, f"未知预设: {preset_key}")
    return {"key": preset_key, "payload": payload}


# ============ 用户预设 CRUD ============

class UserPresetBody(BaseModel):
    key: Optional[str] = None
    label: str
    description: str = ""
    params: Dict[str, Any] = Field(default_factory=dict)


@router.post("/ocr/presets")
def create_user_preset(body: UserPresetBody):
    """新建用户预设（不可覆盖内置 key）。"""
    from antigravity.engine.ocr_presets import OCR_PRESET_MAP, _normalize_params

    label = (body.label or "").strip()
    if not label:
        raise HTTPException(400, "预设名称不能为空")
    key = (body.key or "").strip() or _slug_key(label)
    if key in OCR_PRESET_MAP:
        raise HTTPException(400, f"「{key}」是内置预设，请换名称")
    presets = _user_presets()
    if any(p.get("key") == key for p in presets):
        raise HTTPException(400, f"预设 key 已存在: {key}")
    item = {
        "key": key,
        "label": label,
        "description": (body.description or "").strip(),
        "params": _normalize_params(body.params or {}),
    }
    presets.append(item)
    _save_user_presets(presets)
    return {"ok": True, "preset": item}


@router.put("/ocr/presets/{preset_key}")
def update_user_preset(preset_key: str, body: UserPresetBody):
    """更新用户预设。"""
    from antigravity.engine.ocr_presets import OCR_PRESET_MAP, _normalize_params

    if preset_key in OCR_PRESET_MAP:
        raise HTTPException(400, "内置预设不可修改，请另存为新预设")
    presets = _user_presets()
    idx = next((i for i, p in enumerate(presets) if p.get("key") == preset_key), -1)
    if idx < 0:
        raise HTTPException(404, f"用户预设不存在: {preset_key}")
    label = (body.label or presets[idx].get("label") or preset_key).strip()
    presets[idx] = {
        "key": preset_key,
        "label": label,
        "description": (body.description if body.description is not None else presets[idx].get("description") or "").strip(),
        "params": _normalize_params(body.params if body.params is not None else presets[idx].get("params") or {}),
    }
    _save_user_presets(presets)
    return {"ok": True, "preset": presets[idx]}


@router.delete("/ocr/presets/{preset_key}")
def delete_user_preset(preset_key: str):
    """删除用户预设。"""
    from antigravity.engine.ocr_presets import OCR_PRESET_MAP

    if preset_key in OCR_PRESET_MAP:
        raise HTTPException(400, "内置预设不可删除")
    presets = _user_presets()
    new_list = [p for p in presets if p.get("key") != preset_key]
    if len(new_list) == len(presets):
        raise HTTPException(404, f"用户预设不存在: {preset_key}")
    _save_user_presets(new_list)
    # 若当前选中被删，回退到推荐预设
    ocr = config.data.get("ocr_api", {})
    if ocr.get("preset") == preset_key:
        config.update_section("ocr_api", {"preset": "paper_photo", "custom_params": {}})
    return {"ok": True}


# ============ LLM Provider 列表 ============

@router.get("/extract_llm/providers")
def get_llm_providers():
    """返回所有支持的 LLM Provider 及其默认 URL。"""
    from antigravity.engine.medical_extractor.engine import PROVIDER_DEFAULT_URLS
    return [
        {"name": name, "default_url": url}
        for name, url in PROVIDER_DEFAULT_URLS.items()
    ] + [
        {"name": "Claude", "default_url": "https://api.anthropic.com/v1/messages"},
        {"name": "自定义", "default_url": ""},
    ]


# ============ OCR 配置写入 ============

class OCRSettings(BaseModel):
    url: Optional[str] = None
    model: Optional[str] = None
    preset: Optional[str] = None
    custom_params: Optional[Dict[str, Any]] = None
    token: Optional[str] = None


@router.put("/ocr")
def update_ocr(body: OCRSettings):
    updates: Dict[str, Any] = {}
    if body.url is not None:
        updates["url"] = body.url
    if body.model is not None:
        updates["model"] = body.model
    if body.preset is not None:
        updates["preset"] = body.preset
    if body.custom_params is not None:
        from antigravity.engine.ocr_presets import _normalize_params
        updates["custom_params"] = _normalize_params(body.custom_params)
    if updates:
        config.update_section("ocr_api", updates)
    if body.token is not None:
        config.set_secret("ocr_api", body.token)
    return {"ok": True}


# ============ OCR 测试连接 ============

class TestOCRRequest(BaseModel):
    url: Optional[str] = None
    token: Optional[str] = None
    model: Optional[str] = None


@router.post("/ocr/test")
def test_ocr_connection(body: TestOCRRequest):
    """测试 OCR 接口连接。发一个简单请求看是否能拿到 jobId。"""
    import requests as req

    url = (body.url or config.data.get("ocr_api", {}).get("url", "")).rstrip("/")
    token = body.token or config.get_secret("ocr_api")
    model = body.model or config.data.get("ocr_api", {}).get("model", "PaddleOCR-VL-1.5")

    if not url:
        return {"ok": False, "message": "接口地址未配置"}
    if not token:
        return {"ok": False, "message": "Token 未配置"}

    try:
        # 用一个极小的测试图片（1x1 像素 PNG）
        import base64
        # 1x1 transparent PNG
        tiny_png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        )
        import io
        files = {"file": ("test.png", io.BytesIO(tiny_png), "image/png")}
        data = {"model": model, "optionalPayload": "{}"}
        headers = {"Authorization": f"bearer {token}"}
        resp = req.post(url, headers=headers, data=data, files=files, timeout=15)
        if resp.status_code == 200:
            payload = resp.json()
            job_id = payload.get("data", {}).get("jobId")
            if job_id:
                return {"ok": True, "message": f"连接成功，Job ID: {job_id[:16]}…"}
            return {"ok": True, "message": "连接成功（未返回 jobId，但接口可达）"}
        elif resp.status_code == 401:
            return {"ok": False, "message": "Token 无效或已过期（401）"}
        elif resp.status_code == 403:
            return {"ok": False, "message": "无权限访问（403）"}
        else:
            return {"ok": False, "message": f"HTTP {resp.status_code}: {resp.text[:200]}"}
    except req.Timeout:
        return {"ok": False, "message": "请求超时（15秒），请检查网络或接口地址"}
    except req.ConnectionError:
        return {"ok": False, "message": "无法连接，请检查接口地址是否正确"}
    except Exception as exc:
        return {"ok": False, "message": f"测试失败: {exc}"}


# ============ 抽取 LLM 配置写入 ============

class ExtractLLMSettings(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


@router.put("/extract_llm")
def update_extract_llm(body: ExtractLLMSettings):
    updates = {k: v for k, v in body.dict(exclude={"api_key"}).items() if v is not None}
    if updates:
        config.update_section("extract_llm", updates)
    if body.api_key is not None:
        config.set_secret("extract_llm", body.api_key)
    return {"ok": True}


# ============ LLM 测试连接 ============

class TestLLMRequest(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None


@router.post("/extract_llm/test")
def test_llm_connection(body: TestLLMRequest):
    """测试抽取大模型连接。发一个简单的 "你好" 请求。"""
    from antigravity.engine.medical_extractor.engine import create_api_client, PROVIDER_DEFAULT_URLS

    provider = body.provider or config.data.get("extract_llm", {}).get("provider", "DeepSeek")
    model = body.model or config.data.get("extract_llm", {}).get("model", "")
    base_url = body.base_url or config.data.get("extract_llm", {}).get("base_url", "")
    api_key = body.api_key or config.get_secret("extract_llm")

    if not api_key:
        return {"ok": False, "message": "API Key 未配置"}
    if not model:
        return {"ok": False, "message": "模型名称未配置"}

    # 构造临时配置
    test_config = {
        "provider": provider,
        "model": model,
        "api_key": api_key,
        "api_url": base_url or PROVIDER_DEFAULT_URLS.get(provider, PROVIDER_DEFAULT_URLS.get("DeepSeek", "")),
        "temperature": 0.0,
        "max_tokens": 50,
        "timeout": 15,
        "max_retries": 1,
    }

    try:
        client = create_api_client(test_config)
        ok, msg = client.test_connection()
        return {"ok": ok, "message": msg}
    except Exception as exc:
        return {"ok": False, "message": f"测试失败: {exc}"}


# ============ 病例整理 Agent LLM（独立配置） ============

class AgentLLMSettings(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


@router.put("/agent_llm")
def update_agent_llm(body: AgentLLMSettings):
    updates = {k: v for k, v in body.dict(exclude={"api_key"}).items() if v is not None}
    if updates:
        config.update_section("agent_llm", updates)
    if body.api_key is not None:
        config.set_secret("agent_llm", body.api_key)
    return {"ok": True}


@router.post("/agent_llm/test")
def test_agent_llm_connection(body: TestLLMRequest):
    """测试病例整理 Agent 专用 LLM。"""
    from antigravity.engine.medical_extractor.engine import create_api_client, PROVIDER_DEFAULT_URLS

    agent = config.data.get("agent_llm", {}) or {}
    provider = body.provider or agent.get("provider", "DeepSeek")
    model = body.model or agent.get("model", "")
    base_url = body.base_url or agent.get("base_url", "")
    api_key = body.api_key or config.get_secret("agent_llm")

    if not api_key:
        return {"ok": False, "message": "Agent API Key 未配置"}
    if not model:
        return {"ok": False, "message": "模型名称未配置"}

    test_config = {
        "provider": provider,
        "model": model,
        "api_key": api_key,
        "api_url": base_url or PROVIDER_DEFAULT_URLS.get(provider, PROVIDER_DEFAULT_URLS.get("DeepSeek", "")),
        "temperature": 0.0,
        "max_tokens": 50,
        "timeout": 15,
        "max_retries": 1,
    }
    try:
        client = create_api_client(test_config)
        ok, msg = client.test_connection()
        return {"ok": ok, "message": msg}
    except Exception as exc:
        return {"ok": False, "message": f"测试失败: {exc}"}


@router.post("/agent_llm/copy-from-extract")
def copy_agent_llm_from_extract():
    """一键从抽取 LLM 复制到 Agent LLM（不含自动覆盖已有 key 时仍复制引用）。"""
    extract = config.data.get("extract_llm", {}) or {}
    updates = {
        "provider": extract.get("provider") or "",
        "model": extract.get("model") or "",
        "base_url": extract.get("base_url") or "",
        "temperature": extract.get("temperature", 0.2),
        "max_tokens": extract.get("max_tokens", 2000),
    }
    config.update_section("agent_llm", updates)
    # 复制 keyring 引用
    ref = extract.get("api_key_ref") or ""
    if ref:
        config.update_section("agent_llm", {"api_key_ref": ref})
    else:
        # 尝试读出 extract 明文再写入 agent（若可解析）
        key = config.get_secret("extract_llm")
        if key:
            config.set_secret("agent_llm", key)
    return {"ok": True, "message": "已从抽取 LLM 复制到 Agent LLM"}


# ============ 流程配置 ============

class PipelineSettings(BaseModel):
    extraction_template: Optional[str] = None
    output_excel: Optional[str] = None
    make_docx: Optional[bool] = None


@router.put("/pipeline")
def update_pipeline(body: PipelineSettings):
    updates = {k: v for k, v in body.dict().items() if v is not None}
    if updates:
        config.update_section("pipeline", updates)
    return {"ok": True}


# ============ 文件浏览（Electron 环境下用原生对话框，Web 环境用手动输入） ============

class BrowseRequest(BaseModel):
    mode: str = "open"  # open / save / dir
    filter: str = ""  # 如 "Excel (*.xlsx *.xls)"


@router.post("/browse")
def browse_file(body: BrowseRequest):
    """Web 环境下无法打开原生文件对话框，返回提示让用户手动输入路径。
    在 Electron 环境下可通过 IPC 调用原生对话框（未来扩展）。"""
    return {
        "ok": False,
        "message": "请在输入框中手动输入文件路径，或使用 Electron 桌面版获取原生文件选择器",
        "path": "",
    }
