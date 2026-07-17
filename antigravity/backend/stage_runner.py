"""阶段执行引擎：对单个病人单个阶段（或批量）执行，内置 engine 纯逻辑。

与旧 tasks.py 的区别：
- 一次只执行一个阶段（不是全链路），支持 rerun
- 每个阶段有独立的 handler
- 产物写入病人工作目录的约定子目录
- 实时通过回调推送进度 + 日志
- 失败不传染其他病人（continue-on-error）
- 每页/每步完成后立即 save state.json（崩溃可恢复）
"""

from __future__ import annotations

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .patient import IMAGE_EXTS, Patient, StageState

logger = logging.getLogger(__name__)

# 回调类型
OnProgress = Callable[[str, str, int, int, str], None]  # patient_id, stage, current, total, message
OnLog = Callable[[str, str, str, str], None]  # patient_id, stage, level, message
OnStageDone = Callable[[str, str, str, str], None]  # patient_id, stage, status, message
# patient_id, page_dict|None, page_name, error|None, current, total
OnOcrPage = Callable[[str, Optional[dict], str, Optional[str], int, int], None]


class SkipStage(Exception):
    """主动跳过（非错误）。"""


class StageRunner:
    """执行单个病人单个阶段，或批量执行同一阶段。"""

    def __init__(
        self,
        settings: Dict,
        on_progress: Optional[OnProgress] = None,
        on_log: Optional[OnLog] = None,
        on_stage_done: Optional[OnStageDone] = None,
        on_ocr_page: Optional[OnOcrPage] = None,
    ):
        self.settings = settings
        self.on_progress = on_progress or (lambda *a: None)
        self.on_log = on_log or (lambda *a: None)
        self.on_stage_done = on_stage_done or (lambda *a: None)
        self.on_ocr_page = on_ocr_page or (lambda *a: None)
        self._stop_event = threading.Event()

    @property
    def is_stopped(self) -> bool:
        return self._stop_event.is_set()

    @is_stopped.setter
    def is_stopped(self, value: bool) -> None:
        if value:
            self._stop_event.set()
        else:
            self._stop_event.clear()

    def stop(self):
        self._stop_event.set()

    def _parallel_patients(self) -> int:
        from .config_resolve import clamp_parallel_patients
        return clamp_parallel_patients(self.settings.get("max_parallel_patients", 1), 1)

    # ---- 单病人单阶段 ----
    def run_single(self, patient: Patient, stage: str, rerun: bool = False):
        """执行单个病人的单个阶段。"""
        if stage == "source":
            # source 阶段无需执行
            return
        if stage == "export":
            # export 是汇总操作，由 run_export 单独处理
            return

        ss = patient.stages[stage]
        if rerun:
            self._clear_stage_artifacts(patient, stage)

        ss.mark_running()
        patient.save()
        self.on_log(patient.id, stage, "info", f"开始执行：{stage}")
        try:
            handler = self._handlers().get(stage)
            if handler is None:
                raise ValueError(f"未知阶段：{stage}")
            msg = handler(patient)
            ss.mark_done()
            patient.save()
            self.on_stage_done(patient.id, stage, "done", msg or "完成")
            self.on_log(patient.id, stage, "info", msg or "完成")
        except SkipStage as skip:
            ss.mark_skipped(str(skip))
            patient.save()
            self.on_stage_done(patient.id, stage, "skipped", str(skip))
            self.on_log(patient.id, stage, "info", f"跳过：{skip}")
        except Exception as exc:
            ss.mark_error(str(exc))
            patient.save()
            self.on_stage_done(patient.id, stage, "error", str(exc))
            self.on_log(patient.id, stage, "error", str(exc))
            logger.warning("病人 %s 阶段 %s 失败: %s", patient.name, stage, exc)

    # ---- 批量 ----
    def run_batch(self, patients: List[Patient], stage: str, rerun: bool = False):
        """批量执行同一阶段；N>1 时病人级并行，continue-on-error。"""
        if not patients:
            return
        n = min(self._parallel_patients(), len(patients))
        if n <= 1:
            for p in patients:
                if self.is_stopped:
                    break
                self.run_single(p, stage, rerun=rerun)
            return

        self.on_log("", stage, "info", f"批量加速：同时处理 {n} 人 · 共 {len(patients)} 人")
        with ThreadPoolExecutor(max_workers=n) as pool:
            futures = {}
            for p in patients:
                if self.is_stopped:
                    break
                fut = pool.submit(self.run_single, p, stage, rerun)
                futures[fut] = p
            for fut in as_completed(futures):
                try:
                    fut.result()
                except Exception as exc:
                    p = futures[fut]
                    logger.warning("批量任务异常 %s: %s", p.name, exc)

    # ---- 导出（汇总） ----
    def run_export(self, patients: List[Patient], output_path: str) -> str:
        """把所有已抽取病人的结果导出为 Excel。"""
        from antigravity.engine.medical_extractor.engine import export_rows_to_excel

        rows = []
        for p in patients:
            fields = p.get_extracted_fields()
            if fields and isinstance(fields, dict):
                row = dict(fields.get("fields", fields))
                row["_source"] = p.name
                row["_status"] = "success"
                rows.append(row)

        if not rows:
            raise Exception("没有可导出的抽取结果")

        template = self.settings.get("extraction_template", "")
        if not template:
            raise Exception("未选择抽取模板")

        excel_tpl = self._resolve_excel_template(template)
        path = export_rows_to_excel(rows, excel_tpl, output_path,
                                     log_callback=lambda m: self.on_log("", "export", "info", m))
        return path

    # ---- handler 注册 ----
    def _handlers(self) -> Dict[str, Callable]:
        return {
            "preprocess": self._h_preprocess,
            "slice": self._h_slice,
            "ocr": self._h_ocr,
            "merge": self._h_merge,
            "extract": self._h_extract,
            "review": self._h_review,
        }

    @staticmethod
    def _normalize_preprocess_config(cfg: Dict) -> Dict:
        """规整预处理配置：支持新 preset/ops，兼容旧 enhance 扁平参数。"""
        from antigravity.engine.image_preprocess.presets import DEFAULT_PREPROCESS_PRESET

        if not cfg:
            return {
                "preset": DEFAULT_PREPROCESS_PRESET,
                "ops": None,
                "mask_regions": [],
                "roi_regions": [],
                "collect_metrics": True,
            }
        out = dict(cfg)
        # 旧版只有 contrast 等扁平字段 → legacy 预设
        flat_keys = ("contrast", "sharpness", "brightness", "denoise", "binarize", "binarize_threshold")
        has_legacy = any(k in out for k in flat_keys) or isinstance(out.get("enhance_params"), dict)
        if not out.get("preset") and not out.get("ops") and has_legacy:
            out["preset"] = "legacy"
        out.setdefault("preset", DEFAULT_PREPROCESS_PRESET)
        out.setdefault("mask_regions", [])
        out.setdefault("roi_regions", [])
        out.setdefault("collect_metrics", True)
        return out

    # ---- 预处理 ----
    def _h_preprocess(self, p: Patient) -> str:
        from antigravity.engine.image_preprocess import process_folder

        p_data = p.stages["preprocess"].data
        raw_cfg = p_data.get("config_used") or self.settings.get("preprocess_config", {}) or {}
        cfg = self._normalize_preprocess_config(raw_cfg)
        mask_regions = (
            p_data.get("mask_regions")
            or cfg.get("mask_regions")
            or self.settings.get("mask_regions", [])
            or []
        )
        roi_regions = p_data.get("roi_regions") or cfg.get("roi_regions") or []
        cfg = dict(cfg)
        cfg["mask_regions"] = mask_regions
        cfg["roi_regions"] = roi_regions

        version = self._backup_preprocess(p)
        if version:
            self.on_log(p.id, "preprocess", "info", f"已备份当前预处理为 {version}")

        p.preprocess_dir.mkdir(parents=True, exist_ok=True)
        src = Path(p.source_dir)
        files = [f for f in src.rglob("*") if f.is_file() and f.suffix.lower() in IMAGE_EXTS]
        if not files:
            raise Exception("源目录没有可预处理的图片")

        preset = cfg.get("preset") or "paper_photo"
        self.on_log(p.id, "preprocess", "info", f"场景预设: {preset}")

        result = process_folder(
            str(src),
            str(p.preprocess_dir),
            preset=preset,
            ops=cfg.get("ops"),
            mask_regions=mask_regions,
            roi_regions=roi_regions,
            collect_metrics=bool(cfg.get("collect_metrics", True)),
            log=lambda m: self.on_log(p.id, "preprocess", "info", m),
            progress=lambda cur, tot, msg: self.on_progress(p.id, "preprocess", cur, tot, msg),
            is_stopped=lambda: self.is_stopped,
        )

        if self.is_stopped:
            raise Exception("已停止")

        count = int(result.get("done") or 0)
        # 汇总指标
        metrics_summary = []
        better = worse = 0
        for r in result.get("results") or []:
            cmp_ = r.get("compare") or {}
            if cmp_.get("verdict") == "better":
                better += 1
            elif cmp_.get("verdict") == "worse_or_same":
                worse += 1
            if r.get("metrics_after"):
                metrics_summary.append({
                    "file": Path(r.get("input", "")).name,
                    "ms": r.get("ms"),
                    "verdict": cmp_.get("verdict"),
                    "delta": cmp_.get("delta"),
                    "after": r.get("metrics_after"),
                })

        p.stages["preprocess"].data["config_used"] = cfg
        p.stages["preprocess"].data["mask_regions"] = mask_regions
        p.stages["preprocess"].data["roi_regions"] = roi_regions
        p.stages["preprocess"].data["output_count"] = count
        p.stages["preprocess"].data["metrics_summary"] = metrics_summary[:50]
        p.stages["preprocess"].data["metrics_score"] = {"better": better, "worse_or_same": worse}
        if version:
            p.stages["preprocess"].data["last_backup"] = version
        if count == 0:
            raise Exception("预处理全部失败")
        return f"预处理完成：{count} 张 · 提升{better} / 持平或变差{worse}"

    # ---- 切片 ----
    def _h_slice(self, p: Patient) -> str:
        from antigravity.engine.image_slicer import apply_slices
        from .ocr_inputs import list_images

        p_data = p.stages["slice"].data
        regions = p_data.get("regions") or self.settings.get("slice_regions", [])
        if not regions:
            raise SkipStage("未配置切片区域，已跳过")

        # 与 UI 一致：有预处理则切预处理图，否则源图
        if list_images(p.preprocess_dir):
            src = p.preprocess_dir
            base_stage = "preprocess"
        else:
            src = Path(p.source_dir)
            base_stage = "source"

        # 重跑时清旧产物，避免 OCR 混入陈旧切片
        if p.slice_dir.exists():
            import shutil
            shutil.rmtree(p.slice_dir, ignore_errors=True)
        p.slice_dir.mkdir(parents=True, exist_ok=True)

        files = list_images(src)
        total = len(files)
        if total == 0:
            raise Exception("没有可切片的图片")

        self.on_progress(p.id, "slice", 0, total, f"准备切片 {total} 张（底图={base_stage}）…")
        if self.is_stopped:
            raise Exception("已停止")

        s, f, outputs = apply_slices(
            str(src),
            str(p.slice_dir),
            regions,
            log_callback=lambda m: self.on_log(p.id, "slice", "info", m),
            progress=lambda cur, tot, msg: self.on_progress(p.id, "slice", cur, tot, msg),
            is_stopped=lambda: self.is_stopped,
        )
        if self.is_stopped:
            raise Exception("已停止")

        self.on_progress(p.id, "slice", total, total, "切片完成")
        p.stages["slice"].data["regions"] = regions
        p.stages["slice"].data["output_count"] = s
        p.stages["slice"].data["slice_count"] = len(outputs)
        p.stages["slice"].data["base_stage"] = base_stage
        p.stages["slice"].data["outputs"] = [
            {k: v for k, v in o.items() if k != "path"} for o in outputs
        ]
        # 切片变更后默认走切片 OCR
        if p.stages["ocr"].data.get("input_mode") == "full":
            pass  # 尊重用户显式整页
        else:
            p.stages["ocr"].data["input_mode"] = "auto"
        return f"切片：{s} 页 → {len(outputs)} 张（失败 {f}）"

    # ---- OCR ----
    def _h_ocr(self, p: Patient) -> str:
        from antigravity.engine.ocr_client import AsyncOCRClient, save_layout_results
        from .ocr_inputs import build_ocr_page_meta, resolve_ocr_inputs

        token = self.settings.get("ocr_token", "")
        if not token:
            raise Exception("OCR Token 未配置（请在设置中填写）")

        data_source = p.stages["source"].data.get("data_source", "image")
        if data_source in ("text", "excel"):
            raise SkipStage(f"数据源为 {data_source}，无需 OCR")

        plan = resolve_ocr_inputs(p)
        items = plan["items"]
        if plan.get("error") and not items:
            raise Exception(plan["error"])
        if not items:
            raise Exception(plan.get("warning") or "没有可 OCR 的图片（已查切片/预处理/原始目录）")

        mode = plan["effective_mode"]
        self.on_log(
            p.id, "ocr", "info",
            plan["message"]
            + f" · 图源={plan.get('image_source_label') or plan.get('image_source_effective')}"
            + (f" · {plan['warning']}" if plan.get("warning") else ""),
        )
        if plan.get("warning"):
            self.on_log(p.id, "ocr", "warning", plan["warning"])

        p.ocr_dir.mkdir(parents=True, exist_ok=True)
        client = AsyncOCRClient(
            self.settings.get("ocr_url", ""),
            token,
            model=self.settings.get("ocr_model", ""),
            preset=self.settings.get("ocr_preset", "paper_photo"),
            custom_params=self.settings.get("ocr_custom_params", {}),
            user_presets=self.settings.get("ocr_user_presets", []),
            log_callback=lambda m: self.on_log(p.id, "ocr", "info", m),
        )

        done = 0
        total = len(items)
        page_meta_map: Dict[str, dict] = dict(p.stages["ocr"].data.get("page_meta") or {})

        for idx, item in enumerate(items):
            if self.is_stopped:
                break
            fp = item["path"]
            page_no = idx + 1
            label = item.get("display_label") or fp.name
            self.on_progress(p.id, "ocr", page_no, total, f"OCR {label}")
            p.stages["ocr"].data["progress"] = {
                "current": page_no, "total": total, "message": f"OCR {label}",
            }
            p.save()
            try:
                results = client.process_file(fp)
                if results:
                    base = p.ocr_dir / item["page_key"]
                    img_meta = {
                        "stage": item.get("stage") or "source",
                        "relative": item.get("relative") or item.get("name") or "",
                        "name": item.get("name") or fp.name,
                        "page_key": item["page_key"],
                    }
                    save_layout_results(
                        results,
                        base,
                        save_layout=True,
                        image_meta=img_meta,
                    )
                    done += 1
                    meta = build_ocr_page_meta(item)
                    meta["has_layout"] = True
                    page_payload = self._read_ocr_page_payload(p, item["page_key"], meta=meta)
                    page_meta_map[page_payload["page"]] = meta
                    page_meta_map[item["page_key"]] = meta
                    self.on_ocr_page(p.id, page_payload, item["page_key"], None, page_no, total)
                    self.on_log(
                        p.id, "ocr", "info",
                        f"✓ {label} 完成（{page_payload.get('char_count', 0)} 字）",
                    )
                else:
                    self.on_ocr_page(p.id, None, item["page_key"], "无识别结果", page_no, total)
                    self.on_log(p.id, "ocr", "error", f"{label} OCR 无结果")
            except Exception as exc:
                self.on_log(p.id, "ocr", "error", f"{label} OCR 失败：{exc}")
                self.on_ocr_page(p.id, None, item["page_key"], str(exc), page_no, total)

        p.stages["ocr"].data["progress"] = {"current": total, "total": total, "message": "完成"}
        p.stages["ocr"].data["model"] = self.settings.get("ocr_model", "")
        p.stages["ocr"].data["preset"] = self.settings.get("ocr_preset", "original")
        p.stages["ocr"].data["page_count"] = done
        p.stages["ocr"].data["input_mode_effective"] = mode
        p.stages["ocr"].data["image_source_effective"] = plan.get("image_source_effective")
        p.stages["ocr"].data["image_source_requested"] = plan.get("image_source_requested")
        p.stages["ocr"].data["input_count"] = total
        p.stages["ocr"].data["page_meta"] = page_meta_map
        p.save()
        if done == 0:
            raise Exception("所有图片 OCR 均失败")
        return f"OCR：{done}/{total} 张成功（{plan['message']}）"

    # ---- 合并 ----
    def _h_merge(self, p: Patient) -> str:
        from antigravity.engine.markdown_converter.converter import merge_patient_folder

        # 数据源为 text/excel 时，merged.md 已在导入时写入
        data_source = p.stages["source"].data.get("data_source", "image")
        if data_source in ("text", "excel") and p.merged_md.exists():
            text = p.merged_md.read_text(encoding="utf-8")
            p.stages["merge"].mark_done()
            p.stages["merge"].data["char_count"] = len(text)
            p.stages["merge"].data["merged_path"] = "merged.md"
            p.stages["merge"].data["data_source"] = data_source
            return f"文本数据源已就绪：{len(text)} 字（跳过 OCR 合并）"

        if not p.ocr_dir.is_dir():
            raise Exception("尚未 OCR，无可合并内容")

        merged = merge_patient_folder(str(p.ocr_dir), make_docx=self.settings.get("make_docx", False))
        if merged is None:
            raise Exception("OCR 目录内无 Markdown")

        text = merged.read_text(encoding="utf-8")
        # 同步到病人根目录
        p.merged_md.write_text(text, encoding="utf-8")

        p.stages["merge"].data["char_count"] = len(text)
        p.stages["merge"].data["page_count"] = len(p.ocr_pages())
        p.stages["merge"].data["merged_path"] = "merged.md"
        if self.settings.get("make_docx", False) and p.merged_docx.exists():
            p.stages["merge"].data["docx_path"] = "merged.docx"
        return f"合并完成：{len(text)} 字"

    # ---- 抽取 ----
    def _h_extract(self, p: Patient) -> str:
        from antigravity.engine.medical_extractor.engine import MedicalExtractionEngine, load_template_config

        template = self.settings.get("extraction_template", "")
        if not template:
            raise Exception("未选择抽取模板")
        extract_llm = self.settings.get("extract_llm", {})
        if not extract_llm.get("api_key"):
            raise Exception("抽取大模型 API Key 未配置")

        merged_text = p.get_merged_text()
        if not merged_text:
            raise Exception("尚未合并文档，无法抽取")

        self.on_progress(p.id, "extract", 0, 1, "正在调用大模型…")
        p.stages["extract"].data["progress"] = {"current": 0, "total": 1, "message": "调用大模型中…"}
        p.save()

        tpl = load_template_config(template)
        engine = MedicalExtractionEngine(extract_llm, tpl)

        # 如果项目有提示词工程 .md，用它覆盖 engine 的 build_prompt
        prompt_md_path = self.settings.get("prompt_md_path", "")
        if prompt_md_path:
            from pathlib import Path as P
            prompt_file = P(prompt_md_path)
            if prompt_file.exists():
                prompt_md_content = prompt_file.read_text(encoding="utf-8")
                # 覆盖 engine 的 build_prompt 方法
                original_build = engine.build_prompt
                def build_prompt_with_md(emr_content: str, _md=prompt_md_content, _orig=original_build) -> str:
                    return f"{_md}\n\n---\n\n电子病历内容：\n{emr_content}\n\n请以JSON格式返回提取的数据，格式如下：\n{{\n    \"字段1\": \"值1\",\n    \"字段2\": \"值2\"\n}}\n\n注意事项：\n1. 严格按照字段的数据类型返回数据\n2. 日期格式统一为 YYYY-MM-DD\n3. 数字类型不要包含单位，只返回数字\n4. 未提及的字段填 -1\n5. 只返回JSON，不要包含其他解释文字\n"
                engine.build_prompt = build_prompt_with_md

        # 保存 prompt（可追溯）
        prompt = engine.build_prompt(merged_text)
        p.prompt_path.parent.mkdir(parents=True, exist_ok=True)
        p.prompt_path.write_text(prompt, encoding="utf-8")

        row = engine.extract(merged_text, source=p.name)

        # 保存原始响应（如果 engine 有记录的话）
        # 保存抽取结果
        result = {
            "fields": {k: v for k, v in row.items() if not k.startswith("_")},
            "_source": row.get("_source", p.name),
            "_status": row.get("_status", "success"),
            "llm_config": {
                "provider": extract_llm.get("provider", ""),
                "model": extract_llm.get("model", ""),
            },
        }
        p.extracted_json.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        field_count = len(result["fields"])
        p.stages["extract"].data["field_count"] = field_count
        p.stages["extract"].data["llm_config"] = result["llm_config"]
        p.stages["extract"].data["progress"] = {"current": 1, "total": 1, "message": "完成"}
        return f"抽取完成：{field_count} 个字段"

    # ---- 审核（标记完成，实际审核在前端） ----
    def _h_review(self, p: Patient) -> str:
        if not p.get_extracted_fields():
            raise Exception("尚未抽取，无法审核")
        p.stages["review"].data["reviewed"] = True
        return "审核完成"

    # ---- 辅助 ----
    def _clear_stage_artifacts(self, p: Patient, stage: str):
        """rerun 时清除旧产物。预处理先备份再清，便于回退。"""
        import shutil
        if stage == "preprocess" and p.preprocess_dir.exists():
            self._backup_preprocess(p)
            shutil.rmtree(p.preprocess_dir, ignore_errors=True)
        elif stage == "slice" and p.slice_dir.exists():
            shutil.rmtree(p.slice_dir, ignore_errors=True)
        elif stage == "ocr" and p.ocr_dir.exists():
            shutil.rmtree(p.ocr_dir, ignore_errors=True)
        elif stage == "merge":
            p.merged_md.unlink(missing_ok=True)
            p.merged_docx.unlink(missing_ok=True)
        elif stage == "extract":
            p.extracted_json.unlink(missing_ok=True)
            p.raw_response_path.unlink(missing_ok=True)

    def _backup_preprocess(self, p: Patient) -> Optional[str]:
        """备份当前 preprocess/ 到 preprocess_history/vN，最多保留 5 版。返回版本名。"""
        import shutil
        src = p.preprocess_dir
        if not src.is_dir():
            return None
        files = [f for f in src.rglob("*") if f.is_file()]
        if not files:
            return None
        hist = Path(p.work_dir) / "preprocess_history"
        hist.mkdir(parents=True, exist_ok=True)
        existing = sorted(
            [d for d in hist.iterdir() if d.is_dir() and d.name.startswith("v")],
            key=lambda d: int(d.name[1:]) if d.name[1:].isdigit() else 0,
        )
        next_n = 1
        if existing:
            last = existing[-1].name[1:]
            next_n = (int(last) if last.isdigit() else len(existing)) + 1
        version = f"v{next_n}"
        dest = hist / version
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        shutil.copytree(src, dest)
        # 只保留最近 5 版
        existing = sorted(
            [d for d in hist.iterdir() if d.is_dir() and d.name.startswith("v")],
            key=lambda d: int(d.name[1:]) if d.name[1:].isdigit() else 0,
        )
        while len(existing) > 5:
            old = existing.pop(0)
            shutil.rmtree(old, ignore_errors=True)
        return version

    @staticmethod
    def _read_ocr_page_payload(p: Patient, stem: str, meta: Optional[dict] = None) -> dict:
        """读取刚写入的 OCR md，组装前端卡片数据。"""
        text = ""
        md_path = ""
        candidates = list(p.ocr_dir.glob(f"{stem}*.md"))
        if candidates:
            md_file = sorted(candidates)[0]
            try:
                text = md_file.read_text(encoding="utf-8")
            except OSError:
                text = ""
            try:
                md_path = str(md_file.relative_to(p.work_dir))
            except ValueError:
                md_path = md_file.name
            page_key = md_file.stem
        else:
            page_key = f"{stem}_0"
        payload = {
            "page": page_key,
            "text": text,
            "char_count": len(text),
            "md_path": md_path,
            "status": "done",
        }
        if meta:
            payload.update(meta)
        return payload

    def _resolve_excel_template(self, template: str) -> str:
        if template.lower().endswith(".json"):
            data = json.loads(Path(template).read_text(encoding="utf-8"))
            excel = data.get("template_path", "")
            excel_path = Path(excel)
            if not excel_path.is_absolute():
                excel_path = (Path(template).parent / excel_path).resolve()
            if not excel_path.exists():
                raise Exception(f"模板配置里的 template_path 无效：{excel}")
            return str(excel_path)
        return template
