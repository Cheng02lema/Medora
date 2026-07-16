import json
import re
from pathlib import Path

path = Path("IgG4疾病数据提取提示词工程.md")
text = path.read_text(encoding="utf-8")
lines = text.splitlines()
current_category = None
category_full = None
current = None
entries = []
field_key = None
field_lines = None

cat_pattern = re.compile(r"^##\s+(.*)")
var_pattern = re.compile(r"^###\s+\d+\.\s*(.*)")
field_pattern = re.compile(r"^-\s+\*\*(.+?)\*\*\s*：\s*(.*)")


def flush_field():
    global field_key, field_lines, current
    if not current or not field_key:
        return
    value = "\n".join(field_lines).strip()
    current.setdefault("fields", {})
    if field_key in current["fields"] and value:
        current["fields"][field_key] += "\n" + value
    else:
        current["fields"][field_key] = value
    field_key = None
    field_lines = None


def normalize_category(full: str) -> str:
    txt = full.strip()
    if "、" in txt:
        txt = txt.split("、", 1)[1]
    if "（" in txt:
        txt = txt.split("（", 1)[0]
    return txt.strip()


for line in lines:
    cat_match = cat_pattern.match(line)
    if cat_match:
        flush_field()
        if current:
            entries.append(current)
            current = None
        field_key = None
        field_lines = None
        category_full = cat_match.group(1).strip()
        current_category = normalize_category(category_full)
        continue
    var_match = var_pattern.match(line)
    if var_match:
        flush_field()
        if current:
            entries.append(current)
        raw_name = var_match.group(1).strip()
        type_hint = None
        if "（" in raw_name and raw_name.endswith("）"):
            base, _, tail = raw_name.partition("（")
            raw_name = base.strip()
            type_hint = tail.rstrip("）")
        current = {
            "name": raw_name,
            "category": current_category,
            "category_full": category_full,
            "type_hint": type_hint,
            "fields": {}
        }
        field_key = None
        field_lines = None
        continue
    field_match = field_pattern.match(line)
    if field_match and current is not None:
        flush_field()
        field_key = field_match.group(1).strip()
        field_lines = [field_match.group(2).strip()]
        continue
    if field_key and current is not None:
        if line.startswith("  ") or line.startswith("\t") or line.startswith("- ") or line.strip().startswith("- ") or line.startswith("```") or line.strip() == "":
            field_lines.append(line.rstrip())
        else:
            flush_field()

flush_field()
if current:
    entries.append(current)

Path("config/fields.json").write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"extracted {len(entries)} entries")
