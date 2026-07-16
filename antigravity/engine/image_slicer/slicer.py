"""图片切片纯逻辑（无 UI 依赖）。

区域 dict：``{"name", "x1", "y1", "x2", "y2"}`` 或 ``{x,y,width,height}``。
输出：``output/<stem>/<stem>__<region><ext>``，便于 OCR 稳定映射。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from PIL import Image

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}
_SAFE_RE = re.compile(r"[^\w\u4e00-\u9fff\-]+", re.UNICODE)


def safe_region_name(name: str, idx: int = 0) -> str:
    raw = (name or f"region{idx + 1}").strip() or f"region{idx + 1}"
    cleaned = _SAFE_RE.sub("_", raw).strip("._") or f"region{idx + 1}"
    return cleaned[:80]


def apply_slices(
    input_folder: str,
    output_folder: str,
    regions: List[Dict],
    log_callback: Optional[Callable[[str], None]] = None,
    progress: Optional[Callable[[int, int, str], None]] = None,
    is_stopped: Optional[Callable[[], bool]] = None,
) -> Tuple[int, int, List[Dict[str, Any]]]:
    """对 input_folder 内每张图按 regions 裁剪。

    返回 (成功源图数, 失败源图数, 输出文件清单)。
    清单项: parent_stem, region, name, relative, path
    """
    def _log(msg: str):
        if log_callback:
            log_callback(msg)

    if not regions:
        _log("未提供切片区域，跳过切片")
        return 0, 0, []

    in_path = Path(input_folder)
    if not in_path.is_dir():
        raise FileNotFoundError(f"输入目录不存在: {input_folder}")

    image_files = sorted(
        f for f in in_path.rglob("*")
        if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS
    )
    if not image_files:
        _log(f"输入目录没有图片文件: {input_folder}")
        return 0, 0, []

    out_root = Path(output_folder)
    out_root.mkdir(parents=True, exist_ok=True)
    success = 0
    fail = 0
    outputs: List[Dict[str, Any]] = []
    total = len(image_files)

    for idx, fp in enumerate(image_files):
        if is_stopped and is_stopped():
            _log("切片已停止")
            break
        if progress:
            progress(idx + 1, total, f"切片 {fp.name}")
        try:
            img = Image.open(fp)
            w, h = img.size
            stem = fp.stem
            suffix = fp.suffix.lower() or ".jpg"
            out_dir = out_root / stem
            out_dir.mkdir(parents=True, exist_ok=True)
            for r_idx, region in enumerate(regions):
                coords = _region_coords(region, w, h)
                if coords is None:
                    _log(f"跳过无效区域 {region.get('name', r_idx)} @ {fp.name}")
                    continue
                cropped = img.crop(coords)
                rname = safe_region_name(str(region.get("name", "")), r_idx)
                out_name = f"{stem}__{rname}{suffix}"
                out_path = out_dir / out_name
                if suffix in (".jpg", ".jpeg"):
                    cropped.convert("RGB").save(out_path, quality=95)
                else:
                    cropped.save(out_path)
                rel = str(out_path.relative_to(out_root))
                outputs.append({
                    "parent_stem": stem,
                    "parent_name": fp.name,
                    "region": rname,
                    "region_index": r_idx,
                    "name": out_name,
                    "relative": rel.replace("\\", "/"),
                    "path": str(out_path),
                })
            success += 1
            _log(f"✓ {fp.name} → {len(regions)} 区")
        except Exception as exc:
            fail += 1
            _log(f"✗ {fp.name} 切片失败: {exc}")
            logger.warning("切片失败 %s: %s", fp, exc)

    _log(f"切片完成：成功 {success}，失败 {fail}，产出 {len(outputs)} 张")
    return success, fail, outputs


def _region_coords(
    region: Dict,
    img_w: int,
    img_h: int,
) -> Optional[Tuple[int, int, int, int]]:
    """规整为 (left, upper, right, lower)，并裁到图像边界。"""
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
    left, right = min(x1, x2), max(x1, x2)
    top, bottom = min(y1, y2), max(y1, y2)
    left = max(0, min(img_w, left))
    right = max(0, min(img_w, right))
    top = max(0, min(img_h, top))
    bottom = max(0, min(img_h, bottom))
    if right - left < 2 or bottom - top < 2:
        return None
    return (left, top, right, bottom)
