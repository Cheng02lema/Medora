"""从 PaddleOCR-VL 结果提取可标定的版面块（精简 layout）。

真实结构（示例/通过ocr大模型产生的md文档/*_result.json）：
  layoutParsingResults[].prunedResult.parsing_res_list[]
    block_label / block_content / block_bbox [x1,y1,x2,y2]
    block_polygon_points / block_id / block_order
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union


JsonLike = Union[Dict[str, Any], List[Any]]

# 默认不展示、但可保留的标签（UI 可过滤）
NOISE_LABELS = frozenset({
    "number", "footnote", "header", "header_image",
    "footer", "footer_image", "aside_text",
})


def _as_results_list(raw: JsonLike) -> List[Dict[str, Any]]:
    """兼容：job jsonl 行、单 result dict、外层包 result。"""
    if isinstance(raw, list):
        out = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            if "layoutParsingResults" in item:
                out.append(item)
            elif "result" in item and isinstance(item["result"], dict):
                out.append(item["result"])
            else:
                out.append(item)
        return out
    if isinstance(raw, dict):
        if "layoutParsingResults" in raw:
            return [raw]
        if "result" in raw and isinstance(raw["result"], dict):
            return [raw["result"]]
        return [raw]
    return []


def _norm_bbox(bb: Any, width: int, height: int) -> Optional[List[int]]:
    if not bb or not isinstance(bb, (list, tuple)) or len(bb) < 4:
        return None
    try:
        x1, y1, x2, y2 = [float(bb[i]) for i in range(4)]
    except (TypeError, ValueError):
        return None
    left, right = sorted((x1, x2))
    top, bottom = sorted((y1, y2))
    # 轻微越界钳制
    if width > 0 and height > 0:
        left = max(0, min(width, left))
        right = max(0, min(width, right))
        top = max(0, min(height, top))
        bottom = max(0, min(height, bottom))
    if right - left < 1 or bottom - top < 1:
        return None
    return [int(round(left)), int(round(top)), int(round(right)), int(round(bottom))]


def _norm_polygon(poly: Any) -> Optional[List[List[float]]]:
    if not poly or not isinstance(poly, list) or len(poly) < 3:
        return None
    pts = []
    for p in poly:
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            try:
                pts.append([float(p[0]), float(p[1])])
            except (TypeError, ValueError):
                return None
    return pts if len(pts) >= 3 else None


def _clean_text(s: str) -> str:
    if not s:
        return ""
    t = re.sub(r"\s+", " ", str(s)).strip()
    # 去掉常见 latex 噪声短串（可选）
    return t


def extract_layout_pages(
    raw_results: JsonLike,
    *,
    page_key: str = "",
    image_meta: Optional[Dict[str, Any]] = None,
    include_noise: bool = True,
) -> List[Dict[str, Any]]:
    """从 OCR API 原始 results 提取每页 layout。

    返回列表（通常 1 页；多页 PDF 可能 >1）：
      page_key, page_index, image{stage,relative,width,height}, blocks[], stats
    """
    results = _as_results_list(raw_results)
    pages: List[Dict[str, Any]] = []
    page_index = 0
    img_meta = dict(image_meta or {})

    for result in results:
        lpr = result.get("layoutParsingResults") or []
        data_info = result.get("dataInfo") or {}
        for res in lpr:
            if not isinstance(res, dict):
                continue
            pr = res.get("prunedResult") or {}
            width = int(pr.get("width") or data_info.get("width") or 0)
            height = int(pr.get("height") or data_info.get("height") or 0)
            blocks_raw = pr.get("parsing_res_list") or []
            blocks: List[Dict[str, Any]] = []
            skipped = 0
            for b in blocks_raw:
                if not isinstance(b, dict):
                    skipped += 1
                    continue
                label = str(b.get("block_label") or "text")
                text = _clean_text(b.get("block_content") or "")
                bbox = _norm_bbox(b.get("block_bbox"), width, height)
                if bbox is None:
                    # 尝试从 polygon 推 bbox
                    poly = _norm_polygon(b.get("block_polygon_points"))
                    if poly:
                        xs = [p[0] for p in poly]
                        ys = [p[1] for p in poly]
                        bbox = _norm_bbox([min(xs), min(ys), max(xs), max(ys)], width, height)
                if bbox is None:
                    skipped += 1
                    continue
                if not include_noise and label in NOISE_LABELS:
                    skipped += 1
                    continue
                poly = _norm_polygon(b.get("block_polygon_points"))
                bid = b.get("block_id")
                if bid is None:
                    bid = len(blocks)
                blocks.append({
                    "id": int(bid) if str(bid).lstrip("-").isdigit() else len(blocks),
                    "label": label,
                    "text": text,
                    "bbox": bbox,
                    "polygon": poly,
                    "order": b.get("block_order"),
                    "group_id": b.get("group_id"),
                    "noise": label in NOISE_LABELS,
                    "empty": not bool(text),
                })

            # 按 order / id 排序，便于与 md 对齐
            def _sort_key(blk: Dict[str, Any]):
                o = blk.get("order")
                if o is None:
                    return (1, blk.get("id", 0))
                try:
                    return (0, int(o))
                except (TypeError, ValueError):
                    return (1, blk.get("id", 0))

            blocks.sort(key=_sort_key)

            pk = page_key or img_meta.get("page_key") or f"page_{page_index}"
            layout = {
                "page_key": f"{pk}_{page_index}" if page_index or True else pk,
                "base_key": pk,
                "page_index": page_index,
                "image": {
                    "stage": img_meta.get("stage") or "source",
                    "relative": img_meta.get("relative") or img_meta.get("name") or "",
                    "name": img_meta.get("name") or "",
                    "width": width,
                    "height": height,
                },
                "blocks": blocks,
                "stats": {
                    "block_count": len(blocks),
                    "text_blocks": sum(1 for x in blocks if x["label"] == "text"),
                    "empty_blocks": sum(1 for x in blocks if x.get("empty")),
                    "noise_blocks": sum(1 for x in blocks if x.get("noise")),
                    "skipped": skipped,
                },
                "model_settings": pr.get("model_settings") or {},
            }
            # page_key 与 md 命名一致：{base}_0
            layout["page_key"] = f"{pk}_{page_index}"
            pages.append(layout)
            page_index += 1

    return pages


def save_layout_json(layout: Dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(layout, ensure_ascii=False, indent=2), encoding="utf-8")


def load_layout_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def find_layout_path(ocr_dir: Path, page_name: str) -> Optional[Path]:
    """按 OCR 页名找 layout 文件。"""
    if not ocr_dir.is_dir():
        return None
    stem = page_name
    candidates = [
        ocr_dir / f"{stem}.layout.json",
        ocr_dir / f"{stem}_0.layout.json",
    ]
    # page 可能是 stem_0
    if stem.endswith("_0"):
        base = stem[:-2]
        candidates.append(ocr_dir / f"{base}_0.layout.json")
    else:
        candidates.append(ocr_dir / f"{stem}_0.layout.json")
    for c in candidates:
        if c.is_file():
            return c
    # 模糊
    base = stem.replace("_0", "")
    for p in sorted(ocr_dir.glob("*.layout.json")):
        if base in p.stem or p.stem.startswith(base):
            return p
    return None


def hit_test_blocks(
    layout: Dict[str, Any],
    query: str,
    *,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """文本子串命中块（字段溯源用）。"""
    q = (query or "").strip()
    if not q:
        return []
    hits = []
    for b in layout.get("blocks") or []:
        text = b.get("text") or ""
        if q in text:
            hits.append({
                "id": b.get("id"),
                "label": b.get("label"),
                "bbox": b.get("bbox"),
                "snippet": text[:120],
                "score": 1.0,
            })
        if len(hits) >= limit:
            break
    if hits:
        return hits
    # 宽松：去空白后包含
    qq = re.sub(r"\s+", "", q)
    if len(qq) < 2:
        return []
    for b in layout.get("blocks") or []:
        text = re.sub(r"\s+", "", b.get("text") or "")
        if qq in text:
            hits.append({
                "id": b.get("id"),
                "label": b.get("label"),
                "bbox": b.get("bbox"),
                "snippet": (b.get("text") or "")[:120],
                "score": 0.7,
            })
        if len(hits) >= limit:
            break
    return hits
