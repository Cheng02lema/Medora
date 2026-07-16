"""兼容旧 ImagePreprocessor 接口，内部走新流水线。"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, List, Optional

from .pipeline import process_folder, process_image_file
from .presets import DEFAULT_PREPROCESS_PRESET


class ImagePreprocessor:
    """兼容层：config_data 支持 preset/ops/mask_regions/enhance_params。"""

    def __init__(
        self,
        config_data: Optional[Dict] = None,
        config_path: Optional[str] = None,
        log_callback: Optional[Callable[[str], None]] = None,
    ):
        self.config = config_data or {}
        self.log_callback = log_callback
        if config_path and not config_data:
            import json
            try:
                self.config = json.loads(Path(config_path).read_text(encoding="utf-8"))
            except Exception:
                self.config = {}

    def _log(self, message: str):
        if self.log_callback:
            self.log_callback(str(message))

    def process_image(self, input_path: str, output_path: str):
        preset = self.config.get("preset") or DEFAULT_PREPROCESS_PRESET
        ops = self.config.get("ops")
        # 旧 enhance 模式 → legacy 预设
        if not ops and self.config.get("enhance_params") and not self.config.get("preset"):
            preset = "legacy"
        mask = self.config.get("mask_regions") or []
        try:
            process_image_file(
                input_path,
                output_path,
                preset=preset,
                ops=ops,
                mask_regions=mask,
                roi_regions=self.config.get("roi_regions") or [],
                collect_metrics=False,
                log=self._log,
            )
            self._log(f"✓ 已处理: {input_path} -> {output_path}")
        except Exception as exc:
            self._log(f"✗ 处理失败 {input_path}: {exc}")
            raise

    def process_folder(self, input_folder: str, output_folder: str, recursive: bool = False):
        # recursive 参数保留兼容；实现始终 rglob
        preset = self.config.get("preset") or DEFAULT_PREPROCESS_PRESET
        ops = self.config.get("ops")
        if not ops and self.config.get("enhance_params") and not self.config.get("preset"):
            preset = "legacy"
        process_folder(
            input_folder,
            output_folder,
            preset=preset,
            ops=ops,
            mask_regions=self.config.get("mask_regions") or [],
            roi_regions=self.config.get("roi_regions") or [],
            collect_metrics=False,
            log=self._log,
        )
