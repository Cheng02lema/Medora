from pathlib import Path
from typing import Callable, Dict, List, Optional

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter


import json


class ImagePreprocessor:
    """图像预处理器，支持遮盖隐私与增强参数"""

    def __init__(
        self,
        config_data: Optional[Dict] = None,
        config_path: Optional[str] = None,
        log_callback: Optional[Callable[[str], None]] = None,
    ):
        if config_data:
            self.config = config_data
        elif config_path:
            self.config = self._load_config(config_path)
        else:
            self.config = {}
        self.log_callback = log_callback
        self.mask_regions: List[Dict] = self.config.get("mask_regions", [])
        self.enhance_params: Dict = self.config.get(
            "enhance_params",
            {
                "contrast": 2.0,
                "sharpness": 2.0,
                "brightness": 1.2,
                "denoise": False,
                "binarize": True,
                "binarize_threshold": 140,
            },
        )

    def _log(self, message: str):
        if self.log_callback:
            self.log_callback(str(message))
        else:
            print(message)

    def mask_areas(self, image: Image.Image, mask_regions: Optional[List[Dict]] = None) -> Image.Image:
        mask_regions = mask_regions or self.mask_regions
        if not mask_regions:
            return image
        img_copy = image.copy()
        draw = ImageDraw.Draw(img_copy)
        for region in mask_regions:
            x = region.get("x", 0)
            y = region.get("y", 0)
            width = region.get("width", 100)
            height = region.get("height", 100)
            color = region.get("color", "white")
            draw.rectangle([(x, y), (x + width, y + height)], fill=color)
        return img_copy

    def enhance_for_ocr(self, image: Image.Image, params: Optional[Dict] = None) -> Image.Image:
        params = params or self.enhance_params
        img = image.copy()
        if img.mode != "RGB":
            img = img.convert("RGB")

        contrast = params.get("contrast", 1.5)
        if contrast != 1.0:
            img = ImageEnhance.Contrast(img).enhance(contrast)

        sharpness = params.get("sharpness", 1.3)
        if sharpness != 1.0:
            img = ImageEnhance.Sharpness(img).enhance(sharpness)

        brightness = params.get("brightness", 1.1)
        if brightness != 1.0:
            img = ImageEnhance.Brightness(img).enhance(brightness)

        if params.get("denoise", True):
            img = img.filter(ImageFilter.MedianFilter(size=3))

        if params.get("binarize", False):
            img = img.convert("L")
            threshold = params.get("binarize_threshold", 127)
            img = img.point(lambda x: 255 if x > threshold else 0, mode="1")
            img = img.convert("RGB")
        return img

    def process_image(self, input_path: str, output_path: str):
        try:
            img = Image.open(input_path)
            img = self.mask_areas(img)
            img = self.enhance_for_ocr(img)
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            img.save(output_path, quality=95)
            self._log(f"✓ 已处理: {input_path} -> {output_path}")
        except Exception as exc:
            self._log(f"✗ 处理失败 {input_path}: {exc}")

    def process_folder(self, input_folder: str, output_folder: str, recursive: bool = False):
        input_path = Path(input_folder)
        output_path = Path(output_folder)
        image_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".gif"}

        if recursive:
            files = [f for f in input_path.rglob("*") if f.suffix.lower() in image_extensions]
        else:
            files = [f for f in input_path.glob("*") if f.suffix.lower() in image_extensions]

        if not files:
            self._log(f"警告: 在 {input_folder} 中没有找到图像文件")
            return

        self._log(f"找到 {len(files)} 个图像文件，开始处理...")
        for file_path in files:
            rel = file_path.relative_to(input_path)
            out_file = output_path / rel
            self.process_image(str(file_path), str(out_file))
        self._log(f"处理完成，输出目录: {output_folder}")

    @staticmethod
    def _load_config(config_path: str) -> Dict:
        try:
            with open(config_path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return {}
