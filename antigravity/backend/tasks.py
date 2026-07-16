"""TaskRunner：对一批病人跑完整提取链路，产出四态结果（不暴露子步骤进度）。

内置 engine 纯逻辑。同步实现，由调用方（FastAPI 路由）丢进线程池执行，
通过 on_update 回调把状态变化转发出去（路由层负责转成 WebSocket 推送）。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .patient import Patient

logger = logging.getLogger(__name__)

# on_update(patient, message) —— 每次状态/消息变化时调用
OnUpdate = Callable[[Patient, str], None]


class TaskRunner:
    def __init__(self, patients: List[Patient], options: Dict, on_update: Optional[OnUpdate] = None):
        self.patients = patients
        self.options = options
        self.on_update = on_update or (lambda p, m: None)
        self.is_stopped = False

    def stop(self):
        self.is_stopped = True

    def run(self) -> Dict:
        """跑完整链路，返回汇总 {done, error, output_excel?}。"""
        done = err = 0
        for patient in self.patients:
            if self.is_stopped:
                break
            patient.status = "running"
            patient.error_message = ""
            self._emit(patient, "开始提取…")
            try:
                self._run_patient(patient)
                patient.status = "done"
                done += 1
                self._emit(patient, "提取完成")
            except Exception as exc:  # continue-on-error：单病人失败不影响其他
                patient.status = "error"
                patient.error_message = str(exc)
                err += 1
                logger.warning("病人 %s 提取失败: %s", patient.name, exc)
                self._emit(patient, f"失败：{exc}")
            patient.save()

        output_excel = None
        if self.options.get("extraction_template") and self.options.get("output_excel"):
            try:
                output_excel = self._run_export()
            except Exception as exc:
                logger.warning("导出 Excel 失败: %s", exc)

        return {"done": done, "error": err, "output_excel": output_excel}

    # ---- 单病人整条链 ----
    def _run_patient(self, patient: Patient):
        opts = self.options
        current_dir = Path(patient.source_dir)

        if opts.get("enable_preprocess", True):
            current_dir = self._preprocess(patient, current_dir)
        if opts.get("enable_slice", False):
            current_dir = self._slice(patient, current_dir)

        self._ocr(patient, current_dir)
        self._merge(patient)
        self._extract(patient)

        if opts.get("enable_cleanup", False):
            self._cleanup(patient)

    def _preprocess(self, patient: Patient, src: Path) -> Path:
        from antigravity.engine.image_preprocess import ImagePreprocessor

        pre = ImagePreprocessor(config_data=self.options.get("preprocess_config", {}),
                                log_callback=lambda m: self._emit(patient, m))
        patient.preprocess_dir.mkdir(parents=True, exist_ok=True)
        pre.process_folder(str(src), str(patient.preprocess_dir), recursive=True)
        return patient.preprocess_dir

    def _slice(self, patient: Patient, src: Path) -> Path:
        from antigravity.engine.image_slicer import apply_slices
        import shutil

        regions = self.options.get("slice_regions", [])
        if not regions:
            return src
        if patient.slice_dir.exists():
            shutil.rmtree(patient.slice_dir, ignore_errors=True)
        patient.slice_dir.mkdir(parents=True, exist_ok=True)
        apply_slices(
            str(src),
            str(patient.slice_dir),
            regions,
            log_callback=lambda m: self._emit(patient, m),
        )
        return patient.slice_dir

    def _ocr(self, patient: Patient, src: Path):
        from antigravity.engine.ocr_client import AsyncOCRClient, save_layout_results
        from .ocr_inputs import resolve_ocr_inputs, build_ocr_page_meta

        token = self.options.get("ocr_token", "")
        if not token:
            raise Exception("OCR Token 未配置")
        # 优先走统一解析（有切片则只 OCR 切片）；若调用方传入 src 则兼容
        plan = resolve_ocr_inputs(patient)
        items = plan["items"]
        if not items:
            exts = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif"}
            files = [p for p in src.rglob("*") if p.suffix.lower() in exts] if src.is_dir() else []
            items = [{"path": f, "page_key": f.stem, "display_label": f.name, "stage": "source",
                      "relative": f.name, "name": f.name, "parent_page": f.stem, "region_name": ""} for f in files]
        if plan.get("error") and not items:
            raise Exception(plan["error"])
        if not items:
            raise Exception(plan.get("warning") or f"没有可 OCR 的图片：{src}")
        self._emit(
            patient,
            plan.get("message", f"OCR {len(items)} 张")
            + f" · 图源={plan.get('image_source_label') or plan.get('image_source_effective')}",
        )
        patient.ocr_dir.mkdir(parents=True, exist_ok=True)
        page_meta_map = {}
        client = AsyncOCRClient(
            self.options.get("ocr_url", ""), token,
            model=self.options.get("ocr_model", ""),
            preset=self.options.get("ocr_preset", "original"),
            log_callback=lambda m: self._emit(patient, m),
        )
        done = 0
        for item in items:
            if self.is_stopped:
                break
            fp = item["path"] if isinstance(item, dict) else item
            page_key = item.get("page_key", fp.stem) if isinstance(item, dict) else fp.stem
            results = client.process_file(fp)
            if results:
                img_meta = {}
                if isinstance(item, dict):
                    img_meta = {
                        "stage": item.get("stage") or "source",
                        "relative": item.get("relative") or item.get("name") or "",
                        "name": item.get("name") or getattr(fp, "name", ""),
                        "page_key": page_key,
                    }
                save_layout_results(
                    results,
                    patient.ocr_dir / page_key,
                    save_layout=True,
                    image_meta=img_meta,
                )
                if isinstance(item, dict):
                    meta = build_ocr_page_meta(item)
                    meta["has_layout"] = True
                    page_meta_map[page_key] = meta
                    page_meta_map[f"{page_key}_0"] = meta
                done += 1
        if page_meta_map:
            patient.stages["ocr"].data["page_meta"] = page_meta_map
            patient.stages["ocr"].data["input_mode_effective"] = plan.get("effective_mode", "full")
            patient.stages["ocr"].data["input_count"] = len(items)
        if done == 0:
            raise Exception("所有图片 OCR 均失败")

    def _merge(self, patient: Patient):
        from antigravity.engine.markdown_converter.converter import merge_patient_folder

        merged = merge_patient_folder(str(patient.ocr_dir), make_docx=self.options.get("make_docx", False))
        if merged is None:
            raise Exception("OCR 目录内无可合并的 Markdown")
        text = merged.read_text(encoding="utf-8")
        patient.merged_md.write_text(text, encoding="utf-8")
        patient.merged_text = text

    def _extract(self, patient: Patient):
        from antigravity.engine.medical_extractor.engine import MedicalExtractionEngine, load_template_config

        template = self.options.get("extraction_template", "")
        if not template:
            raise Exception("未选择抽取模板")
        extract_llm = self.options.get("extract_llm", {})
        if not extract_llm.get("api_key"):
            raise Exception("抽取大模型 API Key 未配置")
        tpl = load_template_config(template)
        engine = MedicalExtractionEngine(extract_llm, tpl)
        row = engine.extract(patient.merged_text or "", source=patient.name)
        patient.row = row

    def _cleanup(self, patient: Patient):
        from antigravity.engine.cleanup import delete_matching_files

        pattern = self.options.get("cleanup_pattern", "*右表格_0.md")
        count, _ = delete_matching_files(str(patient.ocr_dir), pattern, dry_run=False)
        self._emit(patient, f"清理 {count} 个文件")

    def _run_export(self) -> str:
        from antigravity.engine.medical_extractor.engine import export_rows_to_excel

        rows = [p.row for p in self.patients if p.status == "done" and p.row]
        if not rows:
            raise Exception("没有可导出的抽取结果")
        template = self.options["extraction_template"]
        output = self.options["output_excel"]
        excel_tpl = self._resolve_excel_template(template)
        return export_rows_to_excel(rows, excel_tpl, output)

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

    def _emit(self, patient: Patient, message: str):
        try:
            self.on_update(patient, message)
        except Exception:
            logger.exception("on_update 回调异常")
