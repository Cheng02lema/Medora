"""轻量预处理算子（OpenCV，无重模型）。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np


def load_bgr(path: str) -> np.ndarray:
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"无法读取图片: {path}")
    return img


def save_bgr(path: str, img: np.ndarray, quality: int = 95) -> None:
    ext = path.lower().rsplit(".", 1)[-1] if "." in path else "jpg"
    if ext in ("jpg", "jpeg"):
        cv2.imwrite(path, img, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
    else:
        cv2.imwrite(path, img)


def op_identity(img: np.ndarray, **_kw) -> np.ndarray:
    return img


def op_resize_max(img: np.ndarray, max_side: int = 3000, **_kw) -> np.ndarray:
    h, w = img.shape[:2]
    m = max(h, w)
    if m <= max_side:
        return img
    scale = max_side / m
    return cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)


def _order_points(pts: np.ndarray) -> np.ndarray:
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    d = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(d)]
    rect[3] = pts[np.argmax(d)]
    return rect


def op_perspective_correct(
    img: np.ndarray,
    min_area_ratio: float = 0.15,
    **_kw,
) -> np.ndarray:
    """检测文档四边形并透视校正；失败则原样返回。"""
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edged = cv2.Canny(blur, 50, 150)
    edged = cv2.dilate(edged, np.ones((3, 3), np.uint8), iterations=1)
    cnts, _ = cv2.findContours(edged, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    cnts = sorted(cnts, key=cv2.contourArea, reverse=True)[:15]
    page = None
    img_area = float(h * w)
    for c in cnts:
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        area = cv2.contourArea(approx)
        if len(approx) == 4 and area > img_area * min_area_ratio:
            page = approx.reshape(4, 2).astype("float32")
            break
    if page is None:
        return img
    rect = _order_points(page)
    (tl, tr, br, bl) = rect
    widthA = np.linalg.norm(br - bl)
    widthB = np.linalg.norm(tr - tl)
    maxW = int(max(widthA, widthB))
    heightA = np.linalg.norm(tr - br)
    heightB = np.linalg.norm(tl - bl)
    maxH = int(max(heightA, heightB))
    if maxW < 50 or maxH < 50:
        return img
    dst = np.array([[0, 0], [maxW - 1, 0], [maxW - 1, maxH - 1], [0, maxH - 1]], dtype="float32")
    M = cv2.getPerspectiveTransform(rect, dst)
    return cv2.warpPerspective(img, M, (maxW, maxH))


def op_deskew(img: np.ndarray, max_angle: float = 15.0, **_kw) -> np.ndarray:
    """小角度旋转校正。"""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    thr = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    coords = np.column_stack(np.where(thr > 0))
    if len(coords) < 100:
        return img
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = 90 + angle
    if abs(angle) < 0.3 or abs(angle) > max_angle:
        return img
    h, w = img.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def op_clahe(img: np.ndarray, clip_limit: float = 2.0, tile: int = 8, **_kw) -> np.ndarray:
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=float(clip_limit), tileGridSize=(int(tile), int(tile)))
    l2 = clahe.apply(l)
    return cv2.cvtColor(cv2.merge([l2, a, b]), cv2.COLOR_LAB2BGR)


def op_shadow_remove(img: np.ndarray, kernel: int = 31, **_kw) -> np.ndarray:
    """背景估计去阴影（文档常用）。"""
    k = max(3, int(kernel) | 1)
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32)
    bg = cv2.medianBlur(img, k)
    bg = cv2.cvtColor(bg, cv2.COLOR_BGR2RGB).astype(np.float32)
    norm = np.clip(rgb / (bg + 1e-3) * 255.0, 0, 255).astype(np.uint8)
    return cv2.cvtColor(norm, cv2.COLOR_RGB2BGR)


def op_bilateral_denoise(img: np.ndarray, d: int = 7, sigma_color: int = 50, sigma_space: int = 50, **_kw) -> np.ndarray:
    return cv2.bilateralFilter(img, int(d), float(sigma_color), float(sigma_space))


def op_demoire_light(img: np.ndarray, **_kw) -> np.ndarray:
    """轻量去摩尔纹：中值 + 轻微高斯，避免糊字。"""
    med = cv2.medianBlur(img, 3)
    return cv2.addWeighted(img, 0.65, med, 0.35, 0)


def op_glare_suppress(img: np.ndarray, thr: int = 245, **_kw) -> np.ndarray:
    """抑制高光反光区域（用邻域填充）。"""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    mask = (gray >= int(thr)).astype(np.uint8) * 255
    if mask.sum() == 0:
        return img
    mask = cv2.dilate(mask, np.ones((5, 5), np.uint8), iterations=1)
    return cv2.inpaint(img, mask, 3, cv2.INPAINT_TELEA)


def op_unsharp(img: np.ndarray, amount: float = 1.2, sigma: float = 1.0, **_kw) -> np.ndarray:
    blur = cv2.GaussianBlur(img, (0, 0), float(sigma))
    return cv2.addWeighted(img, 1 + float(amount), blur, -float(amount), 0)


def op_adaptive_binarize(img: np.ndarray, block: int = 31, C: int = 10, **_kw) -> np.ndarray:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    b = max(3, int(block) | 1)
    bw = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, b, int(C))
    return cv2.cvtColor(bw, cv2.COLOR_GRAY2BGR)


def op_sauvola_like(img: np.ndarray, window: int = 25, k: float = 0.2, **_kw) -> np.ndarray:
    """近似 Sauvola 二值化（手写/纸质可用，截图慎用）。"""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    w = max(3, int(window) | 1)
    mean = cv2.boxFilter(gray, -1, (w, w))
    sqmean = cv2.boxFilter(gray * gray, -1, (w, w))
    std = np.sqrt(np.maximum(sqmean - mean * mean, 0))
    R = 128.0
    thresh = mean * (1 + float(k) * ((std / R) - 1))
    bw = np.where(gray > thresh, 255, 0).astype(np.uint8)
    return cv2.cvtColor(bw, cv2.COLOR_GRAY2BGR)


def op_watermark_suppress(img: np.ndarray, strength: float = 0.35, **_kw) -> np.ndarray:
    """保守水印弱化：同态滤波风格压低频。"""
    s = float(np.clip(strength, 0.05, 0.8))
    img_f = img.astype(np.float32) / 255.0 + 1e-3
    log = np.log(img_f)
    blur = cv2.GaussianBlur(log, (0, 0), 15)
    high = log - blur
    out = np.exp((1 - s) * log + s * high)
    out = np.clip(out * 255.0, 0, 255).astype(np.uint8)
    return out


def op_local_enhance(
    img: np.ndarray,
    regions: Optional[List[Dict[str, Any]]] = None,
    clip_limit: float = 3.0,
    **_kw,
) -> np.ndarray:
    """仅对 ROI 做 CLAHE 局部增强。regions: [{x,y,width,height}] 或 [{x1,y1,x2,y2}]"""
    if not regions:
        return img
    out = img.copy()
    h, w = out.shape[:2]
    for r in regions:
        if "x1" in r:
            x1, y1, x2, y2 = int(r["x1"]), int(r["y1"]), int(r["x2"]), int(r["y2"])
        else:
            x1 = int(r.get("x", 0))
            y1 = int(r.get("y", 0))
            x2 = x1 + int(r.get("width", 0))
            y2 = y1 + int(r.get("height", 0))
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        if x2 - x1 < 4 or y2 - y1 < 4:
            continue
        roi = out[y1:y2, x1:x2]
        out[y1:y2, x1:x2] = op_clahe(roi, clip_limit=clip_limit, tile=4)
    return out


def op_privacy_mask(img: np.ndarray, mask_regions: Optional[List[Dict[str, Any]]] = None, **_kw) -> np.ndarray:
    if not mask_regions:
        return img
    out = img.copy()
    for r in mask_regions:
        if "x1" in r:
            x1, y1, x2, y2 = int(r["x1"]), int(r["y1"]), int(r["x2"]), int(r["y2"])
        else:
            x1 = int(r.get("x", 0))
            y1 = int(r.get("y", 0))
            x2 = x1 + int(r.get("width", 100))
            y2 = y1 + int(r.get("height", 100))
        color = r.get("color", "white")
        bgr = (255, 255, 255) if color == "white" else (0, 0, 0)
        cv2.rectangle(out, (x1, y1), (x2, y2), bgr, thickness=-1)
    return out


# 算子注册表
OPS = {
    "identity": op_identity,
    "resize_max": op_resize_max,
    "perspective_correct": op_perspective_correct,
    "deskew": op_deskew,
    "clahe": op_clahe,
    "shadow_remove": op_shadow_remove,
    "bilateral_denoise": op_bilateral_denoise,
    "demoire_light": op_demoire_light,
    "glare_suppress": op_glare_suppress,
    "unsharp": op_unsharp,
    "adaptive_binarize": op_adaptive_binarize,
    "sauvola": op_sauvola_like,
    "watermark_suppress": op_watermark_suppress,
    "local_enhance": op_local_enhance,
    "privacy_mask": op_privacy_mask,
}

OP_META = {
    "identity": {"label": "原样", "group": "基础", "risk": "low"},
    "resize_max": {"label": "限制最大边", "group": "基础", "risk": "low"},
    "perspective_correct": {"label": "透视校正", "group": "几何", "risk": "medium"},
    "deskew": {"label": "小角度扶正", "group": "几何", "risk": "low"},
    "clahe": {"label": "CLAHE 对比度", "group": "光照", "risk": "low"},
    "shadow_remove": {"label": "去阴影", "group": "光照", "risk": "medium"},
    "bilateral_denoise": {"label": "双边去噪", "group": "增强", "risk": "low"},
    "demoire_light": {"label": "轻量去摩尔纹", "group": "增强", "risk": "medium"},
    "glare_suppress": {"label": "抑制反光", "group": "增强", "risk": "medium"},
    "unsharp": {"label": "反锐化增强", "group": "增强", "risk": "low"},
    "adaptive_binarize": {"label": "自适应二值化", "group": "二值", "risk": "high"},
    "sauvola": {"label": "Sauvola 二值化", "group": "二值", "risk": "high"},
    "watermark_suppress": {"label": "水印弱化", "group": "水印", "risk": "high"},
    "local_enhance": {"label": "ROI 局部增强", "group": "局部", "risk": "low"},
    "privacy_mask": {"label": "隐私遮罩", "group": "遮罩", "risk": "low"},
}
