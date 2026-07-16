"""提示词工程 API：从模板生成字段规则 + LLM增强 + Jinja渲染 + 编辑。

流程:
  Excel模板 → promptforge(VariableLoader + AutoRuleEngine) → 字段定义列表
  → 可选LLM增强 → 字段级规则JSON
  → Jinja渲染(骨架模板 + 项目级提示词 + 字段级规则) → 最终提示词.md
  → 用于实际抽取(engine.build_prompt 读取这个 .md)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
import sys
# 使 antigravity.engine.promptforge 可作为 promptforge 导入
_engine_dir = Path(__file__).resolve().parents[2] / "engine"
if str(_engine_dir) not in sys.path:
    sys.path.insert(0, str(_engine_dir))

from pydantic import BaseModel

from ..state import config, project_store
from ..project import Project

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects/{project_id}/prompt", tags=["prompt"])

# promptforge 工程路径
PROMPT_ENGINEERING_DIR = Path(__file__).resolve().parents[2] / "engine" / "resources" / "prompt_engineering"
DEFAULT_AUTO_RULES = str(PROMPT_ENGINEERING_DIR / "config" / "auto_rules.yaml")
DEFAULT_BLUEPRINT = str(PROMPT_ENGINEERING_DIR / "config" / "prompt_blueprint.yaml")
_ENGINE_DIR = Path(__file__).resolve().parents[2] / "engine"
DEFAULT_TEMPLATE = str(
    (_ENGINE_DIR / "promptforge" / "templates" / "prompt.md.jinja")
    if (_ENGINE_DIR / "promptforge" / "templates" / "prompt.md.jinja").exists()
    else (PROMPT_ENGINEERING_DIR / "promptforge" / "templates" / "prompt.md.jinja")
)


def _get_project(project_id: str) -> Project:
    p = project_store.get(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    return p


# ============ 获取提示词配置 ============

@router.get("")
def get_prompt(project_id: str):
    """获取项目的提示词工程配置。"""
    p = _get_project(project_id)
    return {
        "global": p.prompt_global,
        "fields": p.prompt_fields,
        "engineered_md_path": p.prompt_engineered_md,
        "has_engineered_md": bool(p.prompt_engineered_md and Path(p.prompt_engineered_md).exists()),
    }


# ============ 编辑全局提示词 ============

class UpdateGlobalRequest(BaseModel):
    global_prompt: str


@router.put("/global")
def update_global(project_id: str, req: UpdateGlobalRequest):
    """编辑项目级全局提示词。"""
    p = _get_project(project_id)
    p.prompt_global = req.global_prompt
    p.save()
    return {"ok": True}


# ============ 编辑字段级规则 ============

class UpdateFieldsRequest(BaseModel):
    fields: Dict[str, Any]


@router.put("/fields")
def update_fields(project_id: str, req: UpdateFieldsRequest):
    """编辑字段级规则。"""
    p = _get_project(project_id)
    p.prompt_fields = req.fields
    p.save()
    return {"ok": True}


# ============ 从模板自动生成字段规则 ============

# 项目配置里的 provider 名 → promptforge 工厂名
_PROVIDER_MAP = {
    "openai": "openai",
    "deepseek": "openai",  # OpenAI 兼容协议
    "智谱ai": "openai",
    "通义千问": "dashscope",
    "dashscope": "dashscope",
    "claude": "openai",  # 若 base_url 指向兼容网关
    "azure": "azure",
    "自定义": "openai",
    "custom": "openai",
}

# 常见 provider 默认 base_url（OpenAI 兼容 /chat/completions 前缀的 host）
_PROVIDER_BASE = {
    "DeepSeek": "https://api.deepseek.com/v1",
    "OpenAI": "https://api.openai.com/v1",
    "智谱AI": "https://open.bigmodel.cn/api/paas/v4",
    "通义千问": None,  # dashscope 专用
    "Claude": "https://api.anthropic.com/v1",
}


def _resolve_llm_for_promptforge(project: Project, requested_provider: str = ""):
    """把项目 LLM 配置解析成 promptforge 可用的 provider/base_url/model/api_key。"""
    llm_cfg = project.llm_config or {}
    project_provider = (requested_provider or llm_cfg.get("provider") or "DeepSeek").strip()
    api_key = config.get_secret("extract_llm")
    if not api_key:
        raise HTTPException(
            400,
            "LLM API Key 未配置。请打开「📁 项目设置」→「项目抽取 LLM」填写并保存 API Key。",
        )

    model = (llm_cfg.get("model") or "").strip()
    if not model:
        raise HTTPException(
            400,
            "模型名称未配置。请在「📁 项目设置」→「项目抽取 LLM」填写模型（如 deepseek-chat）。",
        )

    base_url = (llm_cfg.get("base_url") or "").strip() or None
    # 若用户填了完整 chat/completions URL，截成 base
    if base_url and base_url.rstrip("/").endswith("/chat/completions"):
        base_url = base_url.rstrip("/")[: -len("/chat/completions")]

    # 映射 provider
    factory_name = _PROVIDER_MAP.get(project_provider.lower(), _PROVIDER_MAP.get(project_provider, "openai"))
    if factory_name == "openai" and not base_url:
        base_url = _PROVIDER_BASE.get(project_provider) or _PROVIDER_BASE.get("DeepSeek")

    temperature = float(llm_cfg.get("temperature", 0.1) or 0.1)
    # 增强字段定义不需要太高 temperature / 太长输出
    if temperature > 0.5:
        temperature = 0.2
    max_tokens = int(llm_cfg.get("max_tokens", 2000) or 2000)
    if max_tokens > 4000:
        max_tokens = 4000

    return {
        "factory_name": factory_name,
        "project_provider": project_provider,
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }


class GenerateRequest(BaseModel):
    use_llm: bool = False  # 是否使用 LLM 增强
    llm_provider: str = ""  # 可选；默认用项目配置的 provider


@router.post("/generate")
def generate_prompt(project_id: str, req: GenerateRequest):
    """从项目的 Excel 模板自动生成字段规则(dry-run 或 LLM 增强)。"""
    p = _get_project(project_id)
    template_path = p.extraction_template
    if not template_path or not Path(template_path).exists():
        raise HTTPException(
            400,
            "未配置有效的抽取模板路径。请打开「📁 项目设置」选择 Excel 模板后再生成。",
        )

    try:
        from promptforge.cli import enrich_with_llm, load_blueprint
        from promptforge.excel_parser import ExcelReader
        from promptforge.variable_loader import AutoRuleEngine, VariableLoader
    except ImportError as e:
        raise HTTPException(500, f"promptforge 模块加载失败: {e}")

    try:
        # 加载蓝图和 auto_rules
        blueprint = load_blueprint(DEFAULT_BLUEPRINT)
        # 用项目名覆盖蓝图标题，便于 LLM 理解任务
        if p.name:
            blueprint.setdefault("project", {})["title"] = p.name
        if p.prompt_global:
            blueprint.setdefault("project", {})["description"] = p.prompt_global

        reader = ExcelReader(template_path)
        rows = reader.read(None)
        auto_rules = AutoRuleEngine(DEFAULT_AUTO_RULES)
        loader = VariableLoader(auto_rules)
        variables = loader.load(rows)

        if not variables:
            raise HTTPException(400, "模板中未解析到任何字段，请检查 Excel 表头是否正确")

        llm_used = False
        llm_error = ""

        # LLM 增强(可选)
        if req.use_llm:
            try:
                llm = _resolve_llm_for_promptforge(p, req.llm_provider)
                args = SimpleNamespace(
                    dry_run=False,
                    llm_provider=llm["factory_name"],
                    model=llm["model"],
                    temperature=llm["temperature"],
                    max_tokens=llm["max_tokens"],
                    chunk_size=8,  # 字段增强分小批，更稳
                    base_url=llm["base_url"],
                    api_key=llm["api_key"],
                    deployment=None,
                    api_version=None,
                )
                enrich_with_llm(variables, llm["factory_name"], blueprint, args)
                llm_used = True
            except HTTPException:
                raise
            except Exception as e:
                logger.exception("LLM 增强失败")
                # 不整单失败：返回规则生成结果 + 错误说明
                llm_error = str(e)

        # 转换为字段规则 JSON
        fields = {}
        for var in variables:
            fields[var.name] = {
                "category": var.category,
                "variable_type": var.variable_type,
                "description": var.description,
                "synonyms": var.synonyms,
                "rules": var.rules,
                "unit": var.unit,
                "value_rule": var.value_rule,
                "example": var.example,
                "notes": var.notes,
            }

        p.prompt_fields = fields
        p.save()

        msg = f"已生成 {len(fields)} 个字段规则"
        if req.use_llm:
            if llm_used:
                msg += "（已 LLM 增强）"
            else:
                msg += f"（规则已生成，但 LLM 增强失败：{llm_error}）"

        return {
            "ok": True,
            "field_count": len(fields),
            "fields": fields,
            "categories": list(set(v.category for v in variables if v.category)),
            "llm_used": llm_used,
            "llm_error": llm_error,
            "message": msg,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("生成提示词失败")
        raise HTTPException(500, f"生成失败: {e}")


# ============ 渲染最终提示词 .md ============

class RenderRequest(BaseModel):
    project_title: str = ""
    project_version: str = "1.0"
    project_description: str = ""


@router.post("/render")
def render_prompt_md(project_id: str, req: RenderRequest = RenderRequest()):
    """将全局提示词 + 字段级规则渲染为最终提示词 .md。"""
    p = _get_project(project_id)

    try:
        from promptforge.template_renderer import TemplateRenderer
        from jinja2 import Template
    except ImportError as e:
        raise HTTPException(500, f"模板引擎加载失败: {e}")

    try:
        template_path = Path(DEFAULT_TEMPLATE)
        renderer = TemplateRenderer(template_path.parent)

        # 加载蓝图（可被项目级提示词覆盖）
        from promptforge.cli import load_blueprint
        blueprint = load_blueprint(DEFAULT_BLUEPRINT)

        # 覆盖蓝图的项目信息
        if req.project_title:
            blueprint.setdefault("project", {})["title"] = req.project_title
        if req.project_version:
            blueprint.setdefault("project", {})["version"] = req.project_version
        if req.project_description:
            blueprint.setdefault("project", {})["description"] = req.project_description
        elif p.prompt_global:
            blueprint.setdefault("project", {})["description"] = p.prompt_global

        # 从字段级规则构建 sections
        from promptforge.variable_loader import VariableDefinition
        variables = []
        for name, field_data in p.prompt_fields.items():
            var = VariableDefinition(
                name=name,
                category=field_data.get("category", "未分组"),
                variable_type=field_data.get("variable_type", "direct"),
                description=field_data.get("description", ""),
                synonyms=field_data.get("synonyms", []),
                rules=field_data.get("rules", ""),
                unit=field_data.get("unit"),
                value_rule=field_data.get("value_rule"),
                example=field_data.get("example"),
                notes=field_data.get("notes"),
            )
            variables.append(var)

        from promptforge.cli import build_sections
        sections = build_sections(variables, blueprint)

        output_text = renderer.render(
            template_path.name,
            {
                "project": blueprint.get("project", {}),
                "blueprint": blueprint,
                "variable_sections": sections,
                "total_variables": len(variables),
            },
        )

        # 保存到项目工作目录
        p.prompt_dir.mkdir(parents=True, exist_ok=True)
        md_path = p.prompt_dir / "prompt_engineered.md"
        md_path.write_text(output_text, encoding="utf-8")
        p.prompt_engineered_md = str(md_path)
        p.save()

        return {"ok": True, "path": str(md_path), "char_count": len(output_text)}
    except Exception as e:
        logger.exception("渲染提示词失败")
        raise HTTPException(500, f"渲染失败: {e}")


# ============ 获取/编辑最终 .md ============

@router.get("/md")
def get_prompt_md(project_id: str):
    """获取最终渲染的提示词 .md 内容。"""
    p = _get_project(project_id)
    if p.prompt_engineered_md and Path(p.prompt_engineered_md).exists():
        text = Path(p.prompt_engineered_md).read_text(encoding="utf-8")
        return {"text": text, "path": p.prompt_engineered_md, "exists": True}
    return {"text": "", "path": "", "exists": False}


class UpdateMdRequest(BaseModel):
    text: str


@router.put("/md")
def update_prompt_md(project_id: str, req: UpdateMdRequest):
    """手动编辑最终提示词 .md。"""
    p = _get_project(project_id)
    p.prompt_dir.mkdir(parents=True, exist_ok=True)
    md_path = p.prompt_dir / "prompt_engineered.md"
    md_path.write_text(req.text, encoding="utf-8")
    p.prompt_engineered_md = str(md_path)
    p.save()
    return {"ok": True}
