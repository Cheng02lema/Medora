import json
from pathlib import Path

import yaml

entries = json.loads(Path("config/fields.json").read_text(encoding="utf-8"))
use_categories = {
    "基本信息",
    "临床表现",
    "既往史",
    "实验室检查",
    "影像学检查",
    "病理检查",
    "用药指导",
    "数据追溯",
}

category_defaults = {
    "基本信息": "direct",
    "临床表现": "report",
    "既往史": "existence",
    "实验室检查": "numeric",
    "影像学检查": "report",
    "病理检查": "report",
    "用药指导": "report",
    "数据追溯": "memo",
}

name_overrides = {
    "超声": "existence",
    "CT": "existence",
    "MRI": "existence",
    "病理": "existence",
}

syn_delimiters = ["、", "，", " / ", "/", ";", "；", ",", " "]

known_keys = {
    "同义词": "synonyms",
    "描述": "description",
    "规则": "rules",
    "单位": "unit",
    "提取示例": "example",
    "特别注意": "notes",
    "格式要求": "format",
    "必须包含的内容": "required",
}


def split_synonyms(value: str):
    if not value:
        return []
    temp = value
    for sep in ["\n", "、", "，", "；", ";", "/", "\\", ","]:
        temp = temp.replace(sep, "|")
    parts = [item.strip() for item in temp.split("|") if item.strip()]
    return parts


def map_type(entry):
    type_hint = (entry.get("type_hint") or "").strip()
    if "第一类" in type_hint:
        return "direct"
    if "第二类" in type_hint:
        return "existence"
    if "第三类" in type_hint:
        return "report"
    if "第四类" in type_hint:
        return "numeric"
    base = category_defaults.get(entry["category"], "direct")
    return name_overrides.get(entry["name"], base)


exact_fields = {}
for entry in entries:
    if entry["category"] not in use_categories:
        continue
    record = {
        "category": entry["category"],
        "category_full": entry["category_full"],
        "variable_type": map_type(entry),
    }
    extras = []
    for key, label in known_keys.items():
        value = entry["fields"].get(key)
        if not value:
            continue
        if label == "synonyms":
            record[label] = split_synonyms(value)
        else:
            record[label] = value
    for raw_key, raw_value in entry["fields"].items():
        if raw_key in known_keys:
            continue
        extras.append({"label": raw_key, "content": raw_value})
    if extras:
        record["extras"] = extras
    exact_fields[entry["name"]] = record

auto_rules = {
    "defaults": {
        "variable_type": "direct",
        "synonym_delimiters": syn_delimiters,
        "rule_templates": {
            "direct": "提取字段原文，未提及填-1。",
            "existence": "1=存在/阳性；0=明确否认/阴性；-1=未提及。",
            "report": "提取相关检查或描述的关键信息，未提及填-1。",
            "numeric": "提取数值，去掉单位，按取值规则筛选，未提及填-1。",
            "memo": "记录完整思考过程与出处。",
        },
    },
    "exact_fields": exact_fields,
    "patterns": [
        {
            "contains": "报告",
            "variable_type": "report",
            "rules": "提取报告的部位、方式、主要结论，多检查用分号分隔。",
        },
        {
            "suffix": "史",
            "variable_type": "existence",
            "rules": "1=有该病史；0=明确否认；-1=未提及。",
        },
        {
            "contains": "数",
            "variable_type": "numeric",
            "rules": "提取数值并去单位，遵循最大/最小值规则，未提及填-1。",
        },
    ],
}

Path("config/auto_rules.yaml").write_text(
    yaml.dump(auto_rules, allow_unicode=True, sort_keys=False),
    encoding="utf-8",
)
print(f"wrote {len(exact_fields)} fields to auto_rules.yaml")
