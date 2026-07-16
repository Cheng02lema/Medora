from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

import yaml


@dataclass
class VariableDefinition:
    name: str
    category: str
    variable_type: str
    description: str = ""
    synonyms: List[str] = field(default_factory=list)
    rules: str = ""
    unit: Optional[str] = None
    value_rule: Optional[str] = None
    example: Optional[str] = None
    notes: Optional[str] = None
    extra_blocks: List[Dict[str, str]] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    def apply_enrichment(self, payload: Dict[str, Any]) -> None:
        for key in ("category", "variable_type", "description", "rules", "unit", "value_rule", "example", "notes"):
            value = payload.get(key)
            if value:
                setattr(self, key, value)
        if payload.get("synonyms"):
            self.synonyms = payload["synonyms"]
        extra = payload.get("extra") or payload.get("extra_blocks")
        if isinstance(extra, list):
            self.extra_blocks = extra


class AutoRuleEngine:
    def __init__(self, config_path: str) -> None:
        with open(config_path, "r", encoding="utf-8") as fh:
            self.config = yaml.safe_load(fh)
        self.exact_fields = self.config.get("exact_fields", {})
        self.patterns = self.config.get("patterns", [])
        self.defaults = self.config.get("defaults", {})

    def describe(self, name: str) -> Dict[str, Any]:
        if name in self.exact_fields:
            return self.exact_fields[name]
        for _, meta in self.exact_fields.items():
            synonyms = meta.get("synonyms")
            if isinstance(synonyms, list) and name in synonyms:
                return meta
        for pattern in self.patterns:
            if self._match_pattern(name, pattern):
                return pattern
        return {}

    def _match_pattern(self, name: str, pattern: Dict[str, Any]) -> bool:
        text = name.lower()
        if "contains" in pattern and pattern["contains"].lower() not in text:
            return False
        if pattern.get("suffix") and not name.endswith(pattern["suffix"]):
            return False
        if pattern.get("prefix") and not name.startswith(pattern["prefix"]):
            return False
        if pattern.get("regex"):
            return re.search(pattern["regex"], name) is not None
        return True


class VariableLoader:
    HEADER_ALIASES = {
        "category": {"分类", "category", "section", "变量分类", "字段分类"},
        "name": {"字段", "变量", "变量名称", "字段名称", "name"},
        "type": {"类型", "变量类型", "字段类型", "type"},
        "description": {"描述", "说明", "definition"},
        "synonyms": {"同义词", "别名", "关键词"},
        "rules": {"规则", "填写规则", "提取规则"},
        "unit": {"单位", "unit"},
        "value_rule": {"取值规则", "value_rule", "value_strategy"},
        "example": {"示例", "例子", "样例"},
        "notes": {"备注", "注意", "说明"},
        "llm_hint": {"提示", "llm_hint", "LLM提示"},
    }

    def __init__(self, auto_rules: AutoRuleEngine) -> None:
        self.auto_rules = auto_rules

    def load(self, rows: List[List[str]]) -> List[VariableDefinition]:
        if not rows:
            return []
        header_map = self._detect_header(rows[0])
        if header_map and "name" in header_map.values():
            return self._from_table(rows[1:], header_map)
        return self._from_wide_row(rows[0])

    def _detect_header(self, header_row: List[str]) -> Dict[int, str]:
        mapping: Dict[int, str] = {}
        for idx, value in enumerate(header_row):
            text = (value or "").strip()
            lowered = text.lower()
            for canonical, aliases in self.HEADER_ALIASES.items():
                if text in aliases or lowered in aliases:
                    mapping[idx] = canonical
                    break
        return mapping

    def _from_table(self, data_rows: List[List[str]], header_map: Dict[int, str]) -> List[VariableDefinition]:
        definitions: List[VariableDefinition] = []
        for row in data_rows:
            if all((cell is None or str(cell).strip() == "") for cell in row):
                continue
            record: Dict[str, Any] = {}
            for idx, key in header_map.items():
                if idx < len(row):
                    record[key] = str(row[idx]).strip()
            if not record.get("name"):
                continue
            definitions.append(self._build_definition(record))
        return definitions

    def _from_wide_row(self, header_row: List[str]) -> List[VariableDefinition]:
        definitions = []
        for cell in header_row:
            name = (cell or "").strip()
            if not name:
                continue
            definitions.append(self._build_definition({"name": name}))
        return definitions

    def _build_definition(self, record: Dict[str, Any]) -> VariableDefinition:
        name = record.get("name", "").strip()
        hints = self.auto_rules.describe(name)
        category = record.get("category") or hints.get("category") or "未分组"
        variable_type = record.get("type") or hints.get("variable_type") or self.auto_rules.defaults.get("variable_type", "direct")
        synonyms = self._parse_synonyms(record.get("synonyms") or hints.get("synonyms"))
        description = record.get("description") or hints.get("description", "")
        rules = record.get("rules") or hints.get("rules") or self._default_rule(variable_type)
        unit = record.get("unit") or hints.get("unit")
        value_rule = record.get("value_rule") or hints.get("value_rule")
        example = record.get("example") or hints.get("example")
        notes = record.get("notes") or hints.get("notes")
        extra_blocks: List[Dict[str, str]] = []
        hint_extras = hints.get("extras") or []
        if isinstance(hint_extras, list):
            extra_blocks.extend(hint_extras)
        return VariableDefinition(
            name=name,
            category=category,
            variable_type=variable_type,
            description=description,
            synonyms=synonyms,
            rules=rules,
            unit=unit,
            value_rule=value_rule,
            example=example,
            notes=notes,
            extra_blocks=extra_blocks,
            raw=record,
        )

    def _parse_synonyms(self, value: Optional[str] | List[str]) -> List[str]:
        if isinstance(value, list):
            return value
        if not value:
            return []
        delimiters = self.auto_rules.defaults.get("synonym_delimiters", [",", "、", "；", ";"])
        text = str(value)
        pattern = "|".join(re.escape(d) for d in delimiters)
        parts = re.split(pattern, text)
        return [item.strip() for item in parts if item.strip()]

    def _default_rule(self, variable_type: str) -> str:
        templates = self.auto_rules.defaults.get("rule_templates", {})
        return templates.get(variable_type, templates.get("direct", ""))
