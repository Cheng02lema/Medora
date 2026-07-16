"""预处理效果指标：图像质量 + 简单几何，便于 A/B 对比。"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import cv2
import numpy as np


def _to_gray(img: np.ndarray) -> np.ndarray:
    if img.ndim == 2:
        return img
    if img.shape[2] == 4:
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def sharpness_laplacian(gray: np.ndarray) -> float:
    """拉普拉斯方差：越大通常越清晰。"""
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def contrast_std(gray: np.ndarray) -> float:
    return float(np.std(gray.astype(np.float64)))


def brightness_mean(gray: np.ndarray) -> float:
    return float(np.mean(gray.astype(np.float64)))


def noise_estimate(gray: np.ndarray) -> float:
    """基于高通残差的噪声粗估（越小越好）。"""
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    residual = gray.astype(np.float64) - blur.astype(np.float64)
    return float(np.std(residual))


def skew_angle_deg(gray: np.ndarray) -> float:
    """估计主文本倾斜角（度，绝对值越小越水平）。失败返回 0。"""
    try:
        thr = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
        coords = np.column_stack(np.where(thr > 0))
        if len(coords) < 100:
            return 0.0
        rect = cv2.minAreaRect(coords)
        angle = rect[-1]
        if angle < -45:
            angle = 90 + angle
        # minAreaRect 角度语义因版本略有差异，取绝对值作为倾斜程度
        return float(abs(angle) if abs(angle) <= 45 else abs(90 - abs(angle)))
    except Exception:
        return 0.0


def measure_image(img_bgr: np.ndarray) -> Dict[str, float]:
    gray = _to_gray(img_bgr)
    return {
        "sharpness": round(sharpness_laplacian(gray), 3),
        "contrast": round(contrast_std(gray), 3),
        "brightness": round(brightness_mean(gray), 3),
        "noise": round(noise_estimate(gray), 3),
        "skew_deg": round(skew_angle_deg(gray), 3),
        "width": int(img_bgr.shape[1]),
        "height": int(img_bgr.shape[0]),
    }


def measure_path(path: str) -> Dict[str, float]:
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        return {"error": 1.0}
    return measure_image(img)


def compare_metrics(before: Dict[str, float], after: Dict[str, float]) -> Dict[str, Any]:
    """计算 after - before 的有意义差分与简要判定。"""
    keys = ["sharpness", "contrast", "brightness", "noise", "skew_deg"]
    delta = {}
    for k in keys:
        if k in before and k in after:
            delta[k] = round(float(after[k]) - float(before[k]), 3)

    # 粗判定：清晰度升、噪声降、倾斜降 → 更好
    # 注意：锐化会抬高 residual 噪声估计，故噪声上升单独惩罚、不与清晰度双重计分
    score = 0
    d_sharp = delta.get("sharpness", 0)
    d_noise = delta.get("noise", 0)
    d_skew = delta.get("skew_deg", 0)
    d_contrast = delta.get("contrast", 0)

    if d_sharp > 50:
        score += 1
    if d_sharp > 5000:
        score += 1  # 明显更清晰
    if d_noise < -0.5:
        score += 1
    if d_noise > 8:
        score -= 1  # 锐化过猛/噪点明显
    if d_skew < -0.5:
        score += 1
    if d_skew > 0.8:
        score -= 1  # 扶正失败或几何变差
    if d_contrast > 3:
        score += 1
    # 过曝/过暗惩罚
    b = after.get("brightness", 128)
    if b < 40 or b > 220:
        score -= 1

    if score >= 2:
        verdict = "better"
    elif score <= 0:
        verdict = "worse_or_same"
    else:
        verdict = "mixed"

    return {"delta": delta, "score": score, "verdict": verdict}


def text_similarity(a: str, b: str) -> float:
    """简单字符级相似度 0~1（无需额外依赖）。"""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    # 压缩空白
    import re
    aa = re.sub(r"\s+", "", a)
    bb = re.sub(r"\s+", "", b)
    if not aa and not bb:
        return 1.0
    # 基于最长公共子序列近似（对长文本用集合 Jaccard 兜底）
    if len(aa) > 4000 or len(bb) > 4000:
        sa, sb = set(aa), set(bb)
        inter = len(sa & sb)
        union = len(sa | sb) or 1
        return inter / union
    # LCS DP（截断）
    aa, bb = aa[:2000], bb[:2000]
    m, n = len(aa), len(bb)
    prev = [0] * (n + 1)
    for i in range(1, m + 1):
        cur = [0] * (n + 1)
        ca = aa[i - 1]
        for j in range(1, n + 1):
            if ca == bb[j - 1]:
                cur[j] = prev[j - 1] + 1
            else:
                cur[j] = max(prev[j], cur[j - 1])
        prev = cur
    lcs = prev[n]
    return lcs / max(m, n)
