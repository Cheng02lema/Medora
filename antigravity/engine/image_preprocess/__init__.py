"""图像预处理：轻量流水线 + 场景预设 + 指标。"""

from .pipeline import describe_catalog, process_folder, process_image_file
from .presets import DEFAULT_PREPROCESS_PRESET, list_presets
from .processor import ImagePreprocessor  # 兼容旧接口
from .metrics import measure_path, compare_metrics, measure_image

__all__ = [
    "ImagePreprocessor",
    "process_image_file",
    "process_folder",
    "describe_catalog",
    "list_presets",
    "DEFAULT_PREPROCESS_PRESET",
    "measure_path",
    "measure_image",
    "compare_metrics",
]
