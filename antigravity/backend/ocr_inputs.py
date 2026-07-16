"""OCR 输入解析：切片 / 整页 × 预处理图 / 原图。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from .patient import IMAGE_EXTS, Patient

# 结构：auto | slices | full
# 整页图源：auto | preprocess | source
IMAGE_SOURCE_VALUES = ("auto", "preprocess", "source")
INPUT_MODE_VALUES = ("auto", "slices", "full")


def list_images(dir_path: Path) -> List[Path]:
    if not dir_path.is_dir():
        return []
    return sorted(
        p for p in dir_path.rglob("*")
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    )


def slice_images(patient: Patient) -> List[Path]:
    return list_images(patient.slice_dir)


def has_valid_slices(patient: Patient) -> bool:
    return len(slice_images(patient)) > 0


def has_preprocess(patient: Patient) -> bool:
    return bool(list_images(patient.preprocess_dir))


def has_source(patient: Patient) -> bool:
    return bool(list_images(Path(patient.source_dir)))


def get_ocr_input_mode(patient: Patient) -> str:
    """auto | slices | full。默认 auto。"""
    raw = "auto"
    if hasattr(patient.stages["ocr"], "data"):
        raw = patient.stages["ocr"].data.get("input_mode") or "auto"
    mode = str(raw).lower().strip()
    if mode not in INPUT_MODE_VALUES:
        return "auto"
    return mode


def get_ocr_image_source(patient: Patient) -> str:
    """auto | preprocess | source。默认 auto。"""
    raw = "auto"
    if hasattr(patient.stages["ocr"], "data"):
        raw = patient.stages["ocr"].data.get("image_source") or "auto"
    src = str(raw).lower().strip()
    if src not in IMAGE_SOURCE_VALUES:
        return "auto"
    return src


def set_ocr_input_mode(patient: Patient, mode: str) -> str:
    mode = str(mode or "auto").lower().strip()
    if mode not in INPUT_MODE_VALUES:
        mode = "auto"
    patient.stages["ocr"].data["input_mode"] = mode
    return mode


def set_ocr_image_source(patient: Patient, image_source: str) -> str:
    src = str(image_source or "auto").lower().strip()
    if src not in IMAGE_SOURCE_VALUES:
        src = "auto"
    patient.stages["ocr"].data["image_source"] = src
    return src


def set_ocr_input_options(
    patient: Patient,
    mode: Optional[str] = None,
    image_source: Optional[str] = None,
) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if mode is not None:
        out["input_mode"] = set_ocr_input_mode(patient, mode)
    else:
        out["input_mode"] = get_ocr_input_mode(patient)
    if image_source is not None:
        out["image_source"] = set_ocr_image_source(patient, image_source)
    else:
        out["image_source"] = get_ocr_image_source(patient)
    return out


def resolve_mode(patient: Patient) -> str:
    """解析后的结构模式：slices 或 full。"""
    mode = get_ocr_input_mode(patient)
    if mode == "full":
        return "full"
    if mode == "slices":
        return "slices"
    return "slices" if has_valid_slices(patient) else "full"


def resolve_full_page(
    patient: Patient,
    image_source: Optional[str] = None,
) -> Dict[str, Any]:
    """解析整页 OCR 的目录与图源。

    返回 {root, stage, error, image_source_effective}
    """
    req = (image_source or get_ocr_image_source(patient)).lower().strip()
    if req not in IMAGE_SOURCE_VALUES:
        req = "auto"

    pre = patient.preprocess_dir
    src = Path(patient.source_dir)
    pre_files = list_images(pre)
    src_files = list_images(src)

    if req == "source":
        if not src_files:
            return {
                "root": src,
                "stage": "source",
                "error": "源图目录无图片",
                "image_source_effective": "source",
            }
        return {
            "root": src,
            "stage": "source",
            "error": "",
            "image_source_effective": "source",
        }

    if req == "preprocess":
        if not pre_files:
            return {
                "root": pre,
                "stage": "preprocess",
                "error": "已选择预处理图，但尚无预处理产物，请先执行预处理",
                "image_source_effective": "preprocess",
            }
        return {
            "root": pre,
            "stage": "preprocess",
            "error": "",
            "image_source_effective": "preprocess",
        }

    # auto：有预处理用预处理
    if pre_files:
        return {
            "root": pre,
            "stage": "preprocess",
            "error": "",
            "image_source_effective": "preprocess",
        }
    return {
        "root": src,
        "stage": "source",
        "error": "" if src_files else "源图目录无图片",
        "image_source_effective": "source",
    }


def full_page_dir(patient: Patient) -> Path:
    """兼容旧接口：auto 图源。"""
    return resolve_full_page(patient, "auto")["root"]


def _label_for_slice(fp: Path, slice_root: Path, base_stage: str = "") -> Dict[str, Any]:
    rel = str(fp.relative_to(slice_root)).replace("\\", "/")
    stem = fp.stem
    parent_stem = fp.parent.name if fp.parent != slice_root else stem.split("__")[0]
    region = ""
    if "__" in stem:
        region = stem.split("__", 1)[1]
    label = f"{parent_stem} · {region}" if region else parent_stem
    if base_stage:
        label = f"{label}（底图={_stage_cn(base_stage)}）"
    return {
        "path": fp,
        "name": fp.name,
        "relative": rel,
        "stage": "slice",
        "page_key": stem,
        "parent_page": parent_stem,
        "region_name": region,
        "display_label": label,
        "image_source": "slice",
        "slice_base_stage": base_stage,
    }


def _stage_cn(stage: str) -> str:
    return {
        "preprocess": "预处理",
        "source": "原图",
        "slice": "切片",
    }.get(stage, stage or "未知")


def _label_for_full(fp: Path, root: Path, stage: str) -> Dict[str, Any]:
    try:
        rel = str(fp.relative_to(root)).replace("\\", "/")
    except ValueError:
        rel = fp.name
    return {
        "path": fp,
        "name": fp.name,
        "relative": rel,
        "stage": stage,
        "page_key": fp.stem,
        "parent_page": fp.stem,
        "region_name": "",
        "display_label": f"{fp.stem}（{_stage_cn(stage)}）",
        "image_source": stage,
        "slice_base_stage": "",
    }


def resolve_ocr_inputs(patient: Patient) -> Dict[str, Any]:
    """返回 OCR 将使用的输入清单与说明。"""
    requested_mode = get_ocr_input_mode(patient)
    requested_image = get_ocr_image_source(patient)
    effective = resolve_mode(patient)
    items: List[Dict[str, Any]] = []
    warning = ""
    error = ""
    image_source_effective = "source"

    regions_cfg = (patient.stages.get("slice") and patient.stages["slice"].data.get("regions")) or []
    slice_done = patient.stages["slice"].status == "done"
    n_slice = len(slice_images(patient))
    n_pre = len(list_images(patient.preprocess_dir))
    n_src = len(list_images(Path(patient.source_dir)))
    slice_base = (patient.stages["slice"].data or {}).get("base_stage") or ""

    if effective == "slices":
        root = patient.slice_dir
        files = slice_images(patient)
        if not files:
            if requested_mode == "slices":
                warning = "已指定仅切片 OCR，但尚无切片产物"
            effective = "full"
        else:
            items = [_label_for_slice(fp, root, slice_base) for fp in files]
            image_source_effective = "slice"
            base_hint = f" · 切片底图={_stage_cn(slice_base)}" if slice_base else ""
            message = f"输入：{len(items)} 张切片{base_hint}"

    if effective == "full" or not items:
        full = resolve_full_page(patient, requested_image)
        root = full["root"]
        stage = full["stage"]
        image_source_effective = full["image_source_effective"]
        error = full.get("error") or ""
        files = list_images(root) if not error else []
        items = [_label_for_full(fp, root, stage) for fp in files]
        effective = "full"
        if error:
            warning = error
            message = f"输入：整页 0 张 · {_stage_cn(stage)}（不可用）"
        else:
            message = f"输入：整页 {len(items)} 张 · {_stage_cn(stage)}"
        if regions_cfg and not n_slice:
            warning = (warning + "；" if warning else "") + "已框选切片区域但未执行切片，当前将整页 OCR"
        elif regions_cfg and patient.stages["slice"].status == "stale":
            warning = (warning + "；" if warning else "") + "切片结果可能过期，建议重新切片"
        if requested_image == "preprocess" and not n_pre:
            warning = "已选择预处理图，但尚无预处理产物，请先执行预处理"
        if requested_image == "source" and n_pre:
            # 有意跳过预处理
            pass

    if effective == "slices" and items:
        # message 已在切片分支设置
        if "message" not in locals():
            message = f"输入：{len(items)} 张切片"

    serializable = []
    for it in items:
        row = dict(it)
        row["path_str"] = str(it["path"])
        serializable.append(row)

    return {
        "requested_mode": requested_mode,
        "effective_mode": effective,
        "image_source_requested": requested_image,
        "image_source_effective": image_source_effective,
        "count": len(items),
        "items": items,
        "summary": serializable,
        "warning": warning,
        "error": error,
        "has_slices": n_slice > 0,
        "has_preprocess": n_pre > 0,
        "has_source": n_src > 0,
        "preprocess_count": n_pre,
        "source_count": n_src,
        "slice_region_count": len(regions_cfg),
        "slice_status": patient.stages["slice"].status,
        "slice_done": slice_done,
        "slice_base_stage": slice_base,
        "message": message if "message" in locals() else f"输入：{len(items)} 张",
        "image_source_label": _stage_cn(image_source_effective),
        "structure_label": "切片" if effective == "slices" else "整页",
    }


def find_input_for_page(patient: Patient, page_name: str) -> Optional[Dict[str, Any]]:
    """按 OCR 页名找到对应输入图（支持 stem / stem_0 / 模糊）。"""
    plan = resolve_ocr_inputs(patient)
    stem = page_name.replace("_0", "")
    for it in plan["items"]:
        if it["page_key"] == page_name or it["page_key"] == stem:
            return it
        if it["name"] == page_name or Path(it["name"]).stem == stem:
            return it
    for it in plan["items"]:
        if stem in it["page_key"] or it["page_key"] in stem:
            return it
    return None


def build_ocr_page_meta(item: Dict[str, Any]) -> Dict[str, Any]:
    stage = item.get("stage", "source")
    return {
        "source_stage": stage,
        "source_relative": item.get("relative", item.get("name", "")),
        "source_image": item.get("name", ""),
        "parent_page": item.get("parent_page", ""),
        "region_name": item.get("region_name", ""),
        "display_label": item.get("display_label", item.get("page_key", "")),
        "input_mode": "slices" if stage == "slice" else "full",
        "image_source": item.get("image_source") or stage,
        "slice_base_stage": item.get("slice_base_stage") or "",
    }
