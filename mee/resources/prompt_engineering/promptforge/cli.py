from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

import yaml

from .excel_parser import ExcelReader
from .llm_providers import LLMProviderFactory
from .template_renderer import TemplateRenderer
from .variable_loader import AutoRuleEngine, VariableDefinition, VariableLoader


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate prompt-engineering specs from Excel templates.")
    parser.add_argument("--excel", required=True, help="输入的Excel模板路径")
    parser.add_argument("--sheet", default=None, help="可选的工作表名称或索引")
    parser.add_argument("--auto-rules", default="config/auto_rules.yaml", help="字段规则配置文件")
    parser.add_argument("--blueprint", default="config/prompt_blueprint.yaml", help="提示词蓝图配置文件")
    parser.add_argument("--output", default="generated/prompt.md", help="输出Markdown路径")
    parser.add_argument("--template", default="promptforge/templates/prompt.md.jinja", help="Markdown模板文件")
    parser.add_argument("--llm-provider", default=None, help="可选：openai/azure/dashscope/offline")
    parser.add_argument("--model", default="gpt-4o-mini", help="LLM模型或部署名")
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--max-tokens", type=int, default=2000)
    parser.add_argument("--chunk-size", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true", help="跳过LLM调用，仅使用配置生成")
    parser.add_argument("--base-url", default=None, help="可选：自定义LLM Base URL")
    parser.add_argument("--api-key", default=None, help="可选：直接传入API Key")
    parser.add_argument("--deployment", default=None, help="Azure OpenAI部署名")
    parser.add_argument("--api-version", default=None, help="Azure OpenAI API版本")
    return parser.parse_args()


def load_blueprint(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def chunked(seq: List[Any], size: int) -> List[List[Any]]:
    return [seq[i : i + size] for i in range(0, len(seq), max(1, size))]


def enrich_with_llm(
    variables: List[VariableDefinition],
    provider_name: str | None,
    blueprint: Dict[str, Any],
    args: argparse.Namespace,
) -> None:
    if not provider_name or args.dry_run:
        return
    provider = LLMProviderFactory.create(
        provider_name,
        api_key=args.api_key,
        base_url=args.base_url,
        deployment=args.deployment,
        api_version=args.api_version,
    )
    if provider is None:
        return
    llm_config = blueprint.get("llm", {})
    system_prompt = llm_config.get("system_prompt", "")
    user_template = llm_config.get("user_template", "")
    from jinja2 import Template

    template = Template(user_template)
    errors: List[str] = []
    for batch_idx, batch in enumerate(chunked(variables, args.chunk_size)):
        payload = template.render(
            project_title=blueprint.get("project", {}).get("title", "项目"),
            project_version=blueprint.get("project", {}).get("version", "1.0"),
            variables=[
                {
                    "name": item.name,
                    "category": item.category,
                    "raw_hint": item.rules or item.description or "",
                }
                for item in batch
            ],
        )
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": payload})
        try:
            response = provider.complete(
                messages,
                model=args.model,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
                timeout=120,
            )
            data = parse_json_safe(response)
            if not isinstance(data, list):
                raise RuntimeError(f"LLM返回格式异常，期望JSON数组，得到: {type(data).__name__}")
            # 按 name 匹配，避免顺序错位导致字段错乱
            by_name = {
                str(item.get("name", "")).strip(): item
                for item in data
                if isinstance(item, dict) and item.get("name")
            }
            for target in batch:
                item = by_name.get(target.name)
                if item is None and data:
                    # 回退按顺序
                    idx = batch.index(target)
                    if idx < len(data) and isinstance(data[idx], dict):
                        item = data[idx]
                if isinstance(item, dict):
                    target.apply_enrichment(item)
        except Exception as exc:
            errors.append(f"第{batch_idx + 1}批({len(batch)}字段): {exc}")
    if errors and len(errors) == len(chunked(variables, args.chunk_size)):
        # 全部批次失败才抛错
        raise RuntimeError("；".join(errors[:3]))
    if errors:
        # 部分成功：不抛错，由调用方根据字段是否被增强判断
        pass


def parse_json_safe(text: str) -> Any:
    text = (text or "").strip()
    # 去掉 markdown 代码块
    if text.startswith("```"):
        lines = text.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1 and end > start:
            snippet = text[start : end + 1]
            return json.loads(snippet)
        # 尝试对象数组外层
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            snippet = text[start : end + 1]
            obj = json.loads(snippet)
            if isinstance(obj, list):
                return obj
            if isinstance(obj, dict) and "fields" in obj:
                return obj["fields"]
            return [obj]
        raise


def build_sections(variables: List[VariableDefinition], blueprint: Dict[str, Any]) -> List[Dict[str, Any]]:
    config = blueprint.get("categories", {})
    section_map: Dict[str, Dict[str, Any]] = {}
    for name, meta in config.items():
        section_map[name] = {
            "name": name,
            "heading": meta.get("heading", name),
            "description": meta.get("description", ""),
            "order": meta.get("order", 99),
            "variables": [],
        }
    for var in variables:
        section = section_map.get(var.category)
        if not section:
            section = section_map.setdefault(
                var.category,
                {
                    "name": var.category,
                    "heading": var.category,
                    "description": "",
                    "order": 99,
                    "variables": [],
                },
            )
        section["variables"].append(var)
    sections = [meta for meta in section_map.values() if meta["variables"]]
    sections.sort(key=lambda item: item.get("order", 99))
    return sections


def main() -> None:
    args = parse_args()
    blueprint = load_blueprint(args.blueprint)
    reader = ExcelReader(args.excel)
    rows = reader.read(args.sheet)
    auto_rules = AutoRuleEngine(args.auto_rules)
    loader = VariableLoader(auto_rules)
    variables = loader.load(rows)
    enrich_with_llm(variables, args.llm_provider, blueprint, args)
    sections = build_sections(variables, blueprint)
    renderer = TemplateRenderer(Path(args.template).parent)
    output_text = renderer.render(
        Path(args.template).name,
        {
            "project": blueprint.get("project", {}),
            "blueprint": blueprint,
            "variable_sections": sections,
            "total_variables": len(variables),
        },
    )
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(output_text, encoding="utf-8")
    print(f"已生成提示词工程：{output_path}")


if __name__ == "__main__":  # pragma: no cover
    main()
