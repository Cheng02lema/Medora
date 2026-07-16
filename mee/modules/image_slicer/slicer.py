"""图片切片纯逻辑（无 UI 依赖）。

从 ``image_slicer_qt5.py`` 的批处理线程剥离，供主流水线 ``slice`` 步与独立
GUI 共用。切片区域用 dict 表示：``{"name", "x1", "y1", "x2", "y2"}``。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from PIL import Image

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif"}


def apply_slices(
    input_folder: str,
    output_folder: str,
    regions: List[Dict],
    log_callback: Optional[Callable[[str], None]] = None,
) -> Tuple[int, int]:
    """对 input_folder 内每张图片按 regions 裁剪，输出到 output_folder/<图名>/。

    返回 (成功文件数, 失败文件数)。regions 为空时直接返回 (0, 0)。
    """
    def _log(msg: str):
        if log_callback:
            log_callback(msg)

    if not regions:
        _log("未提供切片区域，跳过切片")
        return 0, 0

    in_path = Path(input_folder)
    if not in_path.is_dir():
        raise FileNotFoundError(f"输入目录不存在: {input_folder}")

    image_files = [f for f in os.listdir(input_folder) if Path(f).suffix.lower() in IMAGE_EXTENSIONS]
    if not image_files:
        _log(f"输入目录没有图片文件: {input_folder}")
        return 0, 0

    out_root = Path(output_folder)
    success = 0
    fail = 0
    for filename in image_files:
        try:
            img = Image.open(in_path / filename)
            stem = Path(filename).stem
            suffix = Path(filename).suffix
            out_dir = out_root / stem
            out_dir.mkdir(parents=True, exist_ok=True)
            for region in regions:
                coords = _region_coords(region)
                cropped = img.crop(coords)
                out_name = f"{stem}-{region.get('name', 'slice')}{suffix}"
                cropped.save(out_dir / out_name)
            success += 1
            _log(f"✓ {filename} 切片完成")
        except Exception as exc:
            fail += 1
            _log(f"✗ {filename} 切片失败: {exc}")
            logger.warning("切片失败 %s: %s", filename, exc)
    _log(f"切片完成：成功 {success}，失败 {fail}")
    return success, fail


def _region_coords(region: Dict) -> Tuple[int, int, int, int]:
    """把区域 dict 规整为 (left, upper, right, lower)。"""
    x1 = int(region.get("x1", region.get("x", 0)))
    y1 = int(region.get("y1", region.get("y", 0)))
    if "x2" in region:
        x2 = int(region["x2"])
    else:
        x2 = x1 + int(region.get("width", 0))
    if "y2" in region:
        y2 = int(region["y2"])
    else:
        y2 = y1 + int(region.get("height", 0))
    return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
