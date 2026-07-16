"""可插拔预处理流水线。"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .metrics import compare_metrics, measure_image
from .ops import OPS, OP_META, load_bgr, save_bgr
from .presets import DEFAULT_PREPROCESS_PRESET, get_preset, list_presets


LogFn = Optional[Callable[[str], None]]


def run_ops(
    img,
    ops: List[Dict[str, Any]],
    context: Optional[Dict[str, Any]] = None,
    log: LogFn = None,
) -> Tuple[Any, List[Dict[str, Any]]]:
    """依次执行算子，返回 (结果图, 每步耗时日志)。"""
    ctx = context or {}
    trace: List[Dict[str, Any]] = []
    out = img
    for step in ops:
        op_id = step.get("id") or step.get("op")
        if not step.get("enabled", True):
            continue
        if op_id not in OPS:
            if log:
                log(f"跳过未知算子: {op_id}")
            continue
        params = dict(step.get("params") or {})
        # 注入上下文
        if op_id == "privacy_mask" and "mask_regions" not in params:
            params["mask_regions"] = ctx.get("mask_regions") or []
        if op_id == "local_enhance" and "regions" not in params:
            params["regions"] = ctx.get("roi_regions") or []
        t0 = time.perf_counter()
        try:
            out = OPS[op_id](out, **params)
            ms = (time.perf_counter() - t0) * 1000
            trace.append({"id": op_id, "ok": True, "ms": round(ms, 2)})
        except Exception as exc:
            ms = (time.perf_counter() - t0) * 1000
            trace.append({"id": op_id, "ok": False, "ms": round(ms, 2), "error": str(exc)})
            if log:
                log(f"算子失败 {op_id}: {exc}")
    return out, trace


def process_image_file(
    input_path: str,
    output_path: str,
    preset: str = DEFAULT_PREPROCESS_PRESET,
    ops: Optional[List[Dict[str, Any]]] = None,
    mask_regions: Optional[List[Dict[str, Any]]] = None,
    roi_regions: Optional[List[Dict[str, Any]]] = None,
    collect_metrics: bool = True,
    log: LogFn = None,
) -> Dict[str, Any]:
    """处理单张图并写盘，返回 metrics/trace。"""
    img = load_bgr(input_path)
    before = measure_image(img) if collect_metrics else {}

    if ops is None:
        ops = list(get_preset(preset).get("ops") or [])
    # 末尾始终可挂隐私遮罩
    ops = list(ops)
    if mask_regions:
        ops.append({"id": "privacy_mask", "enabled": True, "params": {"mask_regions": mask_regions}})

    t0 = time.perf_counter()
    out, trace = run_ops(
        img,
        ops,
        context={"mask_regions": mask_regions or [], "roi_regions": roi_regions or []},
        log=log,
    )
    total_ms = (time.perf_counter() - t0) * 1000

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    save_bgr(output_path, out)

    after = measure_image(out) if collect_metrics else {}
    cmp_ = compare_metrics(before, after) if before and after else {}
    return {
        "input": input_path,
        "output": output_path,
        "preset": preset,
        "ms": round(total_ms, 2),
        "trace": trace,
        "metrics_before": before,
        "metrics_after": after,
        "compare": cmp_,
    }


def process_folder(
    input_folder: str,
    output_folder: str,
    preset: str = DEFAULT_PREPROCESS_PRESET,
    ops: Optional[List[Dict[str, Any]]] = None,
    mask_regions: Optional[List[Dict[str, Any]]] = None,
    roi_regions: Optional[List[Dict[str, Any]]] = None,
    collect_metrics: bool = True,
    log: LogFn = None,
    progress: Optional[Callable[[int, int, str], None]] = None,
    is_stopped: Optional[Callable[[], bool]] = None,
) -> Dict[str, Any]:
    exts = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
    in_path = Path(input_folder)
    out_root = Path(output_folder)
    files = [f for f in sorted(in_path.rglob("*")) if f.is_file() and f.suffix.lower() in exts]
    total = len(files)
    results = []
    done = 0
    for idx, fp in enumerate(files):
        if is_stopped and is_stopped():
            break
        rel = fp.relative_to(in_path)
        out = out_root / rel
        if progress:
            progress(idx + 1, total, f"预处理 {fp.name}")
        try:
            r = process_image_file(
                str(fp),
                str(out),
                preset=preset,
                ops=ops,
                mask_regions=mask_regions,
                roi_regions=roi_regions,
                collect_metrics=collect_metrics,
                log=log,
            )
            results.append(r)
            done += 1
        except Exception as exc:
            if log:
                log(f"失败 {fp.name}: {exc}")
            results.append({"input": str(fp), "error": str(exc)})
    return {"total": total, "done": done, "results": results}


def describe_catalog() -> Dict[str, Any]:
    return {
        "presets": list_presets(),
        "ops": [
            {"id": k, **OP_META.get(k, {"label": k, "group": "其他", "risk": "medium"})}
            for k in OPS.keys()
        ],
        "default_preset": DEFAULT_PREPROCESS_PRESET,
    }
