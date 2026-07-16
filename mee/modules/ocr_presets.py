from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


DEFAULT_OCR_PRESET = "original"

BASE_OPTIONAL_PAYLOAD: Dict[str, Any] = {
    "useDocOrientationClassify": False,
    "useDocUnwarping": False,
    "useChartRecognition": False,
}


@dataclass(frozen=True)
class OCRPreset:
    key: str
    label: str
    description: str
    overrides: Dict[str, Any]


OCR_PRESETS: List[OCRPreset] = [
    OCRPreset(
        key="original",
        label="默认（原来）",
        description="保持当前行为，只保留原始基础开关。",
        overrides={},
    ),
    OCRPreset(
        key="screenshot",
        label="屏幕截图",
        description="适合直接截屏，开启版面检测和图片块 OCR。",
        overrides={
            "useLayoutDetection": True,
            "useOcrForImageBlock": True,
            "formatBlockContent": True,
            "mergeLayoutBlocks": True,
            "useTextlineOrientation": True,
            "useChartRecognition": True,
            "useSealRecognition": False,
        },
    ),
    OCRPreset(
        key="screen_photo",
        label="拍摄电脑屏幕",
        description="适合拍屏照片，避免整页朝向误判，保留展平和图片块 OCR。",
        overrides={
            "useLayoutDetection": True,
            "useOcrForImageBlock": True,
            "formatBlockContent": True,
            "mergeLayoutBlocks": True,
            "useDocOrientationClassify": False,
            "useDocUnwarping": True,
            "useTextlineOrientation": True,
            "useSealRecognition": False,
        },
    ),
    OCRPreset(
        key="paper_photo",
        label="拍摄纸质报告",
        description="适合纸质材料拍照，避免整页朝向误判，保留展平和印章识别。",
        overrides={
            "useLayoutDetection": True,
            "useOcrForImageBlock": True,
            "formatBlockContent": True,
            "mergeLayoutBlocks": True,
            "useDocOrientationClassify": False,
            "useDocUnwarping": True,
            "useTextlineOrientation": True,
            "useSealRecognition": True,
        },
    ),
    OCRPreset(
        key="maximum_recall",
        label="最强通用（尽量不漏）",
        description="适合混合来源保底识别，会更慢且可能多扫重复内容。",
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
        },
    ),
]

OCR_PRESET_MAP = {preset.key: preset for preset in OCR_PRESETS}


def get_ocr_preset_options() -> List[Tuple[str, str]]:
    return [(preset.label, preset.key) for preset in OCR_PRESETS]


def get_ocr_preset_label(preset_key: str) -> str:
    return OCR_PRESET_MAP.get(preset_key, OCR_PRESET_MAP[DEFAULT_OCR_PRESET]).label


def get_ocr_preset_description(preset_key: str) -> str:
    return OCR_PRESET_MAP.get(preset_key, OCR_PRESET_MAP[DEFAULT_OCR_PRESET]).description


def build_optional_payload(preset_key: str) -> Dict[str, Any]:
    preset = OCR_PRESET_MAP.get(preset_key, OCR_PRESET_MAP[DEFAULT_OCR_PRESET])
    payload = dict(BASE_OPTIONAL_PAYLOAD)
    payload.update(preset.overrides)
    return payload
