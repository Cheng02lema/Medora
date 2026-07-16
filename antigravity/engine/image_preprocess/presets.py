"""预处理场景预设。"""

from __future__ import annotations

from typing import Any, Dict, List


# 每项: {id, enabled, params}
def _ops(*items: Dict[str, Any]) -> List[Dict[str, Any]]:
    return list(items)


PREPROCESS_PRESETS: Dict[str, Dict[str, Any]] = {
    "skip": {
        "key": "skip",
        "label": "跳过（原图）",
        "description": "不做任何处理，适合清晰扫描/已处理好的图。",
        "ops": _ops(
            {"id": "identity", "enabled": True, "params": {}},
        ),
    },
    "screenshot": {
        "key": "screenshot",
        "label": "屏幕截图",
        "description": "轻量锐化，避免过度二值化。",
        "ops": _ops(
            {"id": "resize_max", "enabled": True, "params": {"max_side": 3000}},
            {"id": "unsharp", "enabled": True, "params": {"amount": 0.6, "sigma": 0.8}},
        ),
    },
    "screen_photo": {
        "key": "screen_photo",
        "label": "拍摄电子屏",
        "description": "抑制反光/摩尔纹，提升对比，不做硬二值。",
        "ops": _ops(
            {"id": "resize_max", "enabled": True, "params": {"max_side": 2800}},
            {"id": "glare_suppress", "enabled": True, "params": {"thr": 245}},
            {"id": "demoire_light", "enabled": True, "params": {}},
            {"id": "clahe", "enabled": True, "params": {"clip_limit": 2.0, "tile": 8}},
            {"id": "unsharp", "enabled": True, "params": {"amount": 0.8, "sigma": 1.0}},
        ),
    },
    "paper_photo": {
        "key": "paper_photo",
        "label": "纸质病历拍照（推荐）",
        "description": "透视校正 + 去阴影 + CLAHE + 轻锐化，主场景默认。",
        "ops": _ops(
            {"id": "resize_max", "enabled": True, "params": {"max_side": 3000}},
            {"id": "perspective_correct", "enabled": True, "params": {"min_area_ratio": 0.12}},
            {"id": "deskew", "enabled": True, "params": {"max_angle": 12}},
            {"id": "shadow_remove", "enabled": True, "params": {"kernel": 31}},
            {"id": "clahe", "enabled": True, "params": {"clip_limit": 2.5, "tile": 8}},
            {"id": "bilateral_denoise", "enabled": True, "params": {"d": 5, "sigma_color": 40, "sigma_space": 40}},
            {"id": "unsharp", "enabled": True, "params": {"amount": 1.0, "sigma": 1.0}},
        ),
    },
    "handwritten": {
        "key": "handwritten",
        "label": "手写病历",
        "description": "保守增强，避免硬二值毁掉笔迹。",
        "ops": _ops(
            {"id": "resize_max", "enabled": True, "params": {"max_side": 3000}},
            {"id": "deskew", "enabled": True, "params": {"max_angle": 10}},
            {"id": "shadow_remove", "enabled": True, "params": {"kernel": 25}},
            {"id": "clahe", "enabled": True, "params": {"clip_limit": 2.0, "tile": 8}},
            {"id": "unsharp", "enabled": True, "params": {"amount": 0.7, "sigma": 0.9}},
        ),
    },
    "watermark_heavy": {
        "key": "watermark_heavy",
        "label": "水印较重",
        "description": "弱化低频水印 + 对比增强（可能伤背景纹理）。",
        "ops": _ops(
            {"id": "resize_max", "enabled": True, "params": {"max_side": 3000}},
            {"id": "watermark_suppress", "enabled": True, "params": {"strength": 0.4}},
            {"id": "clahe", "enabled": True, "params": {"clip_limit": 2.5, "tile": 8}},
            {"id": "unsharp", "enabled": True, "params": {"amount": 0.9, "sigma": 1.0}},
        ),
    },
    "legacy": {
        "key": "legacy",
        "label": "旧版增强（对比用）",
        "description": "接近旧 PIL 全局对比/锐化/可选二值，用于 baseline。",
        "ops": _ops(
            {"id": "clahe", "enabled": True, "params": {"clip_limit": 3.0, "tile": 8}},
            {"id": "unsharp", "enabled": True, "params": {"amount": 1.5, "sigma": 1.2}},
            {"id": "adaptive_binarize", "enabled": False, "params": {"block": 31, "C": 10}},
        ),
    },
}

DEFAULT_PREPROCESS_PRESET = "paper_photo"


def list_presets() -> List[Dict[str, Any]]:
    return [
        {
            "key": p["key"],
            "label": p["label"],
            "description": p["description"],
            "ops": p["ops"],
        }
        for p in PREPROCESS_PRESETS.values()
    ]


def get_preset(key: str) -> Dict[str, Any]:
    return PREPROCESS_PRESETS.get(key) or PREPROCESS_PRESETS[DEFAULT_PREPROCESS_PRESET]
