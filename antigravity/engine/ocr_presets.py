"""PaddleOCR-VL optionalPayload 预设与参数定义。

在线 Job API 使用 camelCase 参数名，写入 optionalPayload JSON 字符串。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


DEFAULT_OCR_PRESET = "paper_photo"
DEFAULT_OCR_MODEL = "PaddleOCR-VL-1.5"

OCR_MODELS = [
    {"id": "PaddleOCR-VL-1.5", "label": "PaddleOCR-VL-1.5"},
    {"id": "PaddleOCR-VL-1.6", "label": "PaddleOCR-VL-1.6（最新）"},
    {"id": "PaddleOCR-VL", "label": "PaddleOCR-VL（v1）"},
]

# 基础默认（未在预设中覆盖的字段）
BASE_OPTIONAL_PAYLOAD: Dict[str, Any] = {
    "useDocOrientationClassify": False,
    "useDocUnwarping": False,
    "useLayoutDetection": True,
    "useChartRecognition": False,
    "useSealRecognition": False,
    "useOcrForImageBlock": False,
    "formatBlockContent": False,
    "mergeLayoutBlocks": True,
    "useTextlineOrientation": False,
    "returnLayoutPolygonPoints": True,
    "visualize": False,
    "markdownIgnoreLabels": [
        "number", "footnote", "header", "header_image",
        "footer", "footer_image", "aside_text",
    ],
    "layoutShapeMode": "auto",
}


# 完整参数 schema（前端面板用）
OCR_PARAM_SCHEMA: List[Dict[str, Any]] = [
    {
        "key": "useDocOrientationClassify",
        "label": "文档朝向分类",
        "type": "bool",
        "default": False,
        "group": "预处理",
        "description": "自动检测整页旋转（0/90/180/270）。纸质拍照建议关，避免误判。",
    },
    {
        "key": "useDocUnwarping",
        "label": "文档展平",
        "type": "bool",
        "default": False,
        "group": "预处理",
        "description": "对弯曲/折皱文档做几何校正。纸质病历拍照建议开。",
    },
    {
        "key": "useLayoutDetection",
        "label": "版面检测",
        "type": "bool",
        "default": True,
        "group": "版面",
        "description": "检测文字/表格/图片/标题等区域。关闭则整图直送 VLM，更快但丢结构。",
    },
    {
        "key": "mergeLayoutBlocks",
        "label": "合并版面块",
        "type": "bool",
        "default": True,
        "group": "版面",
        "description": "合并跨栏或交错的同类版面块。",
    },
    {
        "key": "formatBlockContent",
        "label": "块内容格式化",
        "type": "bool",
        "default": False,
        "group": "版面",
        "description": "将块内容格式化为更规整的 Markdown。",
    },
    {
        "key": "layoutShapeMode",
        "label": "版面形状模式",
        "type": "enum",
        "default": "auto",
        "options": ["auto", "rect", "quad", "poly"],
        "group": "版面",
        "description": "auto/rect/quad/poly。1.5+ 异形框用 auto 或 poly。",
    },
    {
        "key": "useTextlineOrientation",
        "label": "行文字方向",
        "type": "bool",
        "default": False,
        "group": "识别",
        "description": "检测单行横/竖方向。",
    },
    {
        "key": "useOcrForImageBlock",
        "label": "图片块 OCR",
        "type": "bool",
        "default": False,
        "group": "识别",
        "description": "对检测到的图片区域内文字再识别。",
    },
    {
        "key": "useSealRecognition",
        "label": "印章识别",
        "type": "bool",
        "default": False,
        "group": "识别",
        "description": "识别红色印章。病历有公章建议开。",
    },
    {
        "key": "useChartRecognition",
        "label": "图表识别",
        "type": "bool",
        "default": False,
        "group": "识别",
        "description": "解析折线/柱状等图表，较慢。",
    },
    {
        "key": "returnLayoutPolygonPoints",
        "label": "返回版面多边形",
        "type": "bool",
        "default": False,
        "group": "输出",
        "description": "返回版面区域多边形顶点，结果更大。",
    },
    {
        "key": "visualize",
        "label": "输出可视化图",
        "type": "bool",
        "default": False,
        "group": "输出",
        "description": "生成带标注的可视化图，更慢。",
    },
    {
        "key": "markdownIgnoreLabels",
        "label": "Markdown 忽略标签",
        "type": "list",
        "default": [
            "number", "footnote", "header", "header_image",
            "footer", "footer_image", "aside_text",
        ],
        "group": "输出",
        "description": "输出 Markdown 时忽略的版面标签，逗号分隔。空=全部保留。",
    },
]


@dataclass(frozen=True)
class OCRPreset:
    key: str
    label: str
    description: str
    overrides: Dict[str, Any] = field(default_factory=dict)
    builtin: bool = True


OCR_PRESETS: List[OCRPreset] = [
    OCRPreset(
        key="original",
        label="精简默认",
        description="最少开关，速度快，适合清晰扫描件。",
        overrides={
            "useDocOrientationClassify": False,
            "useDocUnwarping": False,
            "useLayoutDetection": True,
            "useChartRecognition": False,
            "useSealRecognition": False,
            "useOcrForImageBlock": False,
            "formatBlockContent": False,
            "mergeLayoutBlocks": True,
            "useTextlineOrientation": False,
        },
    ),
    OCRPreset(
        key="screenshot",
        label="屏幕截图",
        description="适合直接截屏，开版面与图片块 OCR。",
        overrides={
            "useLayoutDetection": True,
            "useOcrForImageBlock": True,
            "formatBlockContent": True,
            "mergeLayoutBlocks": True,
            "useTextlineOrientation": True,
            "useChartRecognition": True,
            "useSealRecognition": False,
            "useDocOrientationClassify": False,
            "useDocUnwarping": False,
        },
    ),
    OCRPreset(
        key="screen_photo",
        label="拍摄电脑屏幕",
        description="拍屏照片：关整页朝向，开展平与行方向。",
        overrides={
            "useLayoutDetection": True,
            "useOcrForImageBlock": True,
            "formatBlockContent": True,
            "mergeLayoutBlocks": True,
            "useDocOrientationClassify": False,
            "useDocUnwarping": True,
            "useTextlineOrientation": True,
            "useSealRecognition": False,
            "useChartRecognition": False,
        },
    ),
    OCRPreset(
        key="paper_photo",
        label="纸质病历（推荐）",
        description="手机拍纸质病历：展平+印章+版面，关整页朝向。",
        overrides={
            "useLayoutDetection": True,
            "useOcrForImageBlock": True,
            "formatBlockContent": True,
            "mergeLayoutBlocks": True,
            "useDocOrientationClassify": False,
            "useDocUnwarping": True,
            "useTextlineOrientation": True,
            "useSealRecognition": True,
            "useChartRecognition": False,
            "layoutShapeMode": "auto",
        },
    ),
    OCRPreset(
        key="maximum_recall",
        label="最强通用",
        description="尽量不漏：全开识别，更慢，可能重复。",
        overrides={
            "useDocOrientationClassify": False,
            "useDocUnwarping": True,
            "useLayoutDetection": True,
            "useChartRecognition": True,
            "useSealRecognition": True,
            "useOcrForImageBlock": True,
            "formatBlockContent": True,
            "mergeLayoutBlocks": True,
            "useTextlineOrientation": True,
            "markdownIgnoreLabels": [],
            "returnLayoutPolygonPoints": True,
            "visualize": False,
            "layoutShapeMode": "auto",
        },
    ),
]

OCR_PRESET_MAP = {p.key: p for p in OCR_PRESETS}


def get_ocr_preset_options() -> List[Tuple[str, str]]:
    return [(p.label, p.key) for p in OCR_PRESETS]


def _normalize_params(params: Dict[str, Any]) -> Dict[str, Any]:
    """规整参数类型。"""
    out: Dict[str, Any] = {}
    schema_map = {s["key"]: s for s in OCR_PARAM_SCHEMA}
    for k, v in (params or {}).items():
        if k not in schema_map and k not in BASE_OPTIONAL_PAYLOAD:
            # 允许透传未知字段（未来兼容）
            out[k] = v
            continue
        schema = schema_map.get(k, {})
        t = schema.get("type")
        if t == "bool":
            out[k] = bool(v)
        elif t == "list":
            if isinstance(v, str):
                out[k] = [x.strip() for x in v.split(",") if x.strip()]
            elif isinstance(v, list):
                out[k] = [str(x) for x in v]
            else:
                out[k] = []
        elif t == "enum":
            opts = schema.get("options") or []
            out[k] = v if v in opts else schema.get("default", "auto")
        else:
            out[k] = v
    return out


def build_optional_payload(
    preset_key: str = DEFAULT_OCR_PRESET,
    user_presets: Optional[List[Dict[str, Any]]] = None,
    custom_params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """生成最终 optionalPayload。

    优先级：BASE → 预设 overrides → custom_params 覆盖。
    """
    payload = dict(BASE_OPTIONAL_PAYLOAD)

    # 内置预设
    if preset_key in OCR_PRESET_MAP:
        payload.update(OCR_PRESET_MAP[preset_key].overrides)
    else:
        # 用户预设
        for up in user_presets or []:
            if up.get("key") == preset_key:
                payload.update(_normalize_params(up.get("params") or {}))
                break

    if custom_params:
        payload.update(_normalize_params(custom_params))

    return payload


def list_presets(user_presets: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """内置 + 用户预设，带完整 params 展开结果。"""
    result = []
    for p in OCR_PRESETS:
        result.append({
            "key": p.key,
            "label": p.label,
            "description": p.description,
            "builtin": True,
            "params": build_optional_payload(p.key),
        })
    for up in user_presets or []:
        key = up.get("key") or ""
        if not key or key in OCR_PRESET_MAP:
            continue
        result.append({
            "key": key,
            "label": up.get("label") or key,
            "description": up.get("description") or "",
            "builtin": False,
            "params": build_optional_payload(key, user_presets=user_presets),
        })
    return result


def resolve_preset_params(
    preset_key: str,
    user_presets: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    if preset_key in OCR_PRESET_MAP or any(u.get("key") == preset_key for u in (user_presets or [])):
        return build_optional_payload(preset_key, user_presets=user_presets)
    return None
