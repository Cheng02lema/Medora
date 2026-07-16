from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

from PyQt5.QtCore import QObject, QThread, pyqtSignal

from .. import PROJECT_ROOT
from ..modules.cleanup import delete_matching_files
from ..modules.image_preprocess import ImagePreprocessor
from ..modules.image_slicer.slicer import apply_slices
from ..modules.markdown_converter.converter import merge_patient_folder
from ..modules.medical_extractor.engine import (
    MedicalExtractionEngine,
    export_rows_to_excel,
    load_template_config,
)
from ..modules.ocr_client import AsyncOCRClient, extract_markdown_text, save_layout_results
from ..modules.payment_ocr import process_payment_images

logger = logging.getLogger(__name__)


@dataclass
class PipelineStep:
    key: str
    title: str
    description: str
    optional: bool = False
    critical: bool = False  # 关键步骤失败则中止整条流水线


# 端到端流水线：选完文件夹 → 一路跑到 结果.xlsx
PIPELINE_STEPS: List[PipelineStep] = [
    PipelineStep("preprocess", "图片增强", "遮盖敏感区域并提升亮度/对比度", optional=True),
    PipelineStep("slice", "图片切片", "按已保存的切片区域裁剪（未配置则跳过）", optional=True),
    PipelineStep("ocr_batch", "批量OCR", "调用 OCR 接口，逐页缓存 Markdown", critical=True),
    PipelineStep("ocr_payment", "缴费补救OCR", "对 -缴费情况.jpg 等单独补救识别", optional=True),
    PipelineStep("merge", "合并病人文档", "把每个病人的逐页 Markdown 合并成一份", critical=True),
    PipelineStep("extract", "大模型结构化抽取", "逐病人调用大模型抽取为结构化数据", critical=True),
    PipelineStep("export", "写入结果Excel", "按模板表头把抽取结果写入 Excel", critical=True),
    PipelineStep("cleanup", "后缀清理", "删除无用的中间 Markdown（如 *右表格_0.md）", optional=True),
]


@dataclass
class PipelineConfig:
    scenario: str
    raw_input: str
    preprocess_output: str
    ocr_output: str
    api_url: str
    api_token: str
    ocr_model: str
    ocr_preset: str
    file_extensions: List[str]
    enable_payment_ocr: bool
    payment_pattern: str
    cleanup_target: str
    cleanup_pattern: str
    selected_steps: List[str]
    extraction_template: str = ""          # Excel 模板 或 template_config.json
    output_excel: str = ""                  # 结果 Excel 输出路径
    extract_llm: Dict = field(default_factory=dict)  # provider/api_key/model/...
    slice_output: str = ""                  # 切片输出目录（可选）
    make_docx: bool = True                  # merge 时是否顺带生成 docx


class StepError(Exception):
    """带用户可读提示的步骤错误。"""

    def __init__(self, message: str):
        super().__init__(message)
        self.user_message = message


class PipelineWorker(QThread):
    log = pyqtSignal(str)
    step_changed = pyqtSignal(str)
    step_completed = pyqtSignal(str, str, str)  # key, state, message
    finished = pyqtSignal(bool, str)

    def __init__(self, config: PipelineConfig):
        super().__init__()
        self.config = config
        self.is_stopped = False
        # 步骤间传递的中间状态
        self._image_dir = config.raw_input      # 当前有效的图片目录
        self._merged_files: List[Path] = []     # 各病人 merged.md 路径
        self._rows: List[Dict] = []             # 抽取得到的行

    # -------- 生命周期 --------
    def stop(self):
        self.is_stopped = True
        self.log.emit("收到停止请求，将在当前步骤安全点中止…")

    def run(self):
        enabled = set(self.config.selected_steps or [s.key for s in PIPELINE_STEPS])
        summary = {"success": [], "error": [], "skipped": []}
        aborted = False

        for step in PIPELINE_STEPS:
            if self.is_stopped:
                self.step_completed.emit(step.key, "skipped", "已取消")
                summary["skipped"].append(step.key)
                continue
            if step.key not in enabled:
                self.step_completed.emit(step.key, "skipped", "本次未选择")
                summary["skipped"].append(step.key)
                continue
            reason = self._skip_reason(step.key)
            if reason:
                self.log.emit(f"[{step.title}] 跳过：{reason}")
                self.step_completed.emit(step.key, "skipped", reason)
                summary["skipped"].append(step.key)
                continue

            self.step_changed.emit(step.key)
            handler = self._handlers()[step.key]
            try:
                handler()
                self.step_completed.emit(step.key, "success", f"{step.title} 完成")
                summary["success"].append(step.key)
            except StepError as exc:
                self.step_completed.emit(step.key, "error", exc.user_message)
                self.log.emit(f"[{step.title}] 失败：{exc.user_message}")
                summary["error"].append(step.key)
                logger.error("步骤 %s 失败: %s", step.key, exc.user_message)
                if step.critical:
                    aborted = True
                    break
            except Exception as exc:  # 未预期错误
                msg = self._friendly_error(step.key, exc)
                self.step_completed.emit(step.key, "error", msg)
                self.log.emit(f"[{step.title}] 失败：{msg}")
                logger.exception("步骤 %s 未预期错误", step.key)
                summary["error"].append(step.key)
                if step.critical:
                    aborted = True
                    break

        success = not aborted and not summary["error"] and not self.is_stopped
        self.finished.emit(success, self._summary_text(summary, aborted))

    # -------- 步骤适用性 --------
    def _skip_reason(self, step_key: str) -> Optional[str]:
        cfg = self.config
        if cfg.scenario == "text" and step_key in {"preprocess", "slice", "ocr_batch", "ocr_payment"}:
            return "文本场景，无需图像处理"
        if step_key == "ocr_payment" and not cfg.enable_payment_ocr:
            return "未启用缴费补救 OCR"
        if step_key == "slice" and not self._slice_regions():
            return "未配置切片区域（可在 模块中心→图片切片工具 框选并保存）"
        return None

    def _handlers(self) -> Dict[str, Callable[[], None]]:
        return {
            "preprocess": self._run_preprocess,
            "slice": self._run_slice,
            "ocr_batch": self._run_batch_ocr,
            "ocr_payment": self._run_payment_ocr,
            "merge": self._run_merge,
            "extract": self._run_extract,
            "export": self._run_export,
            "cleanup": self._run_cleanup,
        }

    # -------- 各步骤实现 --------
    def _run_preprocess(self):
        self.log.emit("开始图片增强 …")
        config_path = PROJECT_ROOT / "mee" / "resources" / "preprocess_config.json"
        config_data = {}
        if config_path.exists():
            try:
                config_data = json.loads(config_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                self.log.emit(f"预处理配置解析失败，使用默认参数：{exc}")
        if not self.config.raw_input or not Path(self.config.raw_input).is_dir():
            raise StepError("原始输入目录不存在，请先在左侧选择病历图片文件夹")
        preprocessor = ImagePreprocessor(config_data=config_data, log_callback=self.log.emit)
        preprocessor.process_folder(self.config.raw_input, self.config.preprocess_output, recursive=True)
        self._image_dir = self.config.preprocess_output

    def _slice_regions(self) -> List[Dict]:
        path = PROJECT_ROOT / "mee" / "resources" / "slice_config.json"
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data.get("regions", [])
        except (json.JSONDecodeError, OSError):
            return []

    def _run_slice(self):
        regions = self._slice_regions()
        out_dir = self.config.slice_output or str(Path(self.config.preprocess_output).parent / "slice")
        self.log.emit(f"开始图片切片：{self._image_dir} → {out_dir}")
        apply_slices(self._image_dir, out_dir, regions, log_callback=self.log.emit)
        self._image_dir = out_dir

    def _run_batch_ocr(self):
        input_dir = self._image_dir or self.config.raw_input
        self.log.emit(f"开始批量 OCR：{input_dir}")
        root = Path(input_dir)
        if not root.is_dir():
            raise StepError(f"OCR 输入目录不存在：{input_dir}")
        files = [p for p in root.rglob("*") if p.suffix.lower() in self.config.file_extensions]
        if not files:
            raise StepError(f"输入目录内没有匹配 {self.config.file_extensions} 的文件")
        if not self.config.api_token:
            raise StepError("OCR Token 未配置，请到 设置→OCR API 填写并测试连接")
        output_dir = Path(self.config.ocr_output)
        output_dir.mkdir(parents=True, exist_ok=True)
        client = AsyncOCRClient(
            self.config.api_url,
            self.config.api_token,
            model=self.config.ocr_model,
            preset=self.config.ocr_preset,
            log_callback=self.log.emit,
        )
        ok = 0
        for idx, file_path in enumerate(files, start=1):
            if self.is_stopped:
                raise StepError(f"已取消（完成 {ok}/{len(files)}）")
            self.log.emit(f"[{idx}/{len(files)}] OCR {file_path.name}")
            try:
                results = client.process_file(file_path)
            except Exception as exc:
                self.log.emit(f"  ✗ {file_path.name} OCR 失败：{exc}")
                continue
            if results:
                self._save_ocr_result(file_path, results, root, output_dir)
                ok += 1
        if ok == 0:
            raise StepError("所有文件 OCR 均失败，请检查接口地址/Token/网络")
        self.log.emit(f"OCR 完成：{ok}/{len(files)} 个文件成功")

    def _save_ocr_result(self, file_path: Path, results, root: Path, output_dir: Path):
        rel = file_path.relative_to(root)
        base = output_dir / rel.parent / rel.stem
        base.parent.mkdir(parents=True, exist_ok=True)
        save_layout_results(results, base)

    def _run_payment_ocr(self):
        self.log.emit("补救识别缴费单据 …")
        if not self.config.api_token:
            raise StepError("OCR Token 未配置，无法进行缴费补救识别")
        process_payment_images(
            input_dir=self.config.raw_input,
            output_dir=self.config.ocr_output,
            api_url=self.config.api_url,
            token=self.config.api_token,
            model=self.config.ocr_model,
            preset=self.config.ocr_preset,
            pattern=self.config.payment_pattern,
            log_callback=self.log.emit,
        )

    def _run_merge(self):
        ocr_root = Path(self.config.ocr_output)
        if not ocr_root.is_dir():
            raise StepError(f"OCR 输出目录不存在：{ocr_root}")
        patient_dirs = [d for d in sorted(ocr_root.iterdir()) if d.is_dir()]
        if not patient_dirs:
            raise StepError("OCR 输出目录内没有病人子目录，无法合并")
        self.log.emit(f"开始合并 {len(patient_dirs)} 个病人的文档 …")
        self._merged_files = []
        for d in patient_dirs:
            if self.is_stopped:
                raise StepError("已取消")
            merged = merge_patient_folder(str(d), make_docx=self.config.make_docx)
            if merged:
                self._merged_files.append(merged)
                self.log.emit(f"  ✓ {d.name} 已合并")
            else:
                self.log.emit(f"  · {d.name} 无可合并 Markdown，跳过")
        if not self._merged_files:
            raise StepError("没有任何病人目录成功合并")

    def _run_extract(self):
        if not self._merged_files:
            raise StepError("没有可抽取的合并文档（合并步骤未产出）")
        if not self.config.extraction_template:
            raise StepError("未选择抽取模板，请在左侧指定 Excel 模板或字段配置 JSON")
        if not self.config.extract_llm.get("api_key"):
            raise StepError("抽取大模型 API Key 未配置，请到 设置→病历提取 LLM 填写")
        try:
            template_config = load_template_config(self.config.extraction_template)
        except (FileNotFoundError, ValueError) as exc:
            raise StepError(f"读取抽取模板失败：{exc}") from exc

        engine = MedicalExtractionEngine(self.config.extract_llm, template_config)
        self._rows = []
        total = len(self._merged_files)
        for idx, merged in enumerate(self._merged_files, start=1):
            if self.is_stopped:
                raise StepError(f"已取消（完成 {idx - 1}/{total}）")
            patient = merged.parent.name
            self.log.emit(f"[{idx}/{total}] 抽取 {patient}")
            content = merged.read_text(encoding="utf-8")
            try:
                row = engine.extract(content, source=patient)
            except Exception as exc:
                self.log.emit(f"  ✗ {patient} 抽取失败：{exc}")
                # 保留失败行以便在 Excel 中标红，不中断其他病人
                row = {"_source": patient, "_status": "failed", "_error_message": str(exc)}
            self._rows.append(row)
        succeeded = sum(1 for r in self._rows if r.get("_status") == "success")
        self.log.emit(f"抽取完成：{succeeded}/{total} 个病人成功")
        if succeeded == 0:
            raise StepError("所有病人抽取均失败，请检查大模型配置与网络")

    def _run_export(self):
        if not self._rows:
            raise StepError("没有可导出的数据（抽取步骤未产出）")
        output = self.config.output_excel
        if not output:
            output = str(Path(self.config.ocr_output).parent / "结果.xlsx")
        excel_template = self._resolve_excel_template()
        try:
            path = export_rows_to_excel(self._rows, excel_template, output, log_callback=self.log.emit)
        except Exception as exc:
            raise StepError(f"写入 Excel 失败：{exc}") from exc
        self.log.emit(f"✓ 结果已写入：{path}")

    def _resolve_excel_template(self) -> str:
        """导出需要一个 .xlsx 模板；若用户选的是字段配置 JSON，则取其中的
        template_path 指向的真实 Excel。"""
        tpl = self.config.extraction_template
        if tpl.lower().endswith(".json"):
            json_path = Path(tpl)
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                raise StepError(f"读取模板配置失败：{exc}") from exc
            excel = data.get("template_path", "")
            if not excel:
                raise StepError("字段配置 JSON 缺少 template_path，请指向真实 Excel 模板")
            excel_path = Path(excel)
            if not excel_path.is_absolute():
                # 相对路径按 JSON 文件所在目录解析
                excel_path = (json_path.parent / excel_path).resolve()
            if not excel_path.exists():
                raise StepError(f"字段配置里的 template_path 不存在：{excel}")
            return str(excel_path)
        return tpl

    def _run_cleanup(self):
        target = self.config.cleanup_target
        if not target:
            self.log.emit("未指定清理目录，跳过")
            return
        count, _ = delete_matching_files(target, self.config.cleanup_pattern, dry_run=False)
        self.log.emit(f"已清理 {count} 个匹配文件")

    # -------- 辅助 --------
    def _friendly_error(self, step_key: str, exc: Exception) -> str:
        hints = {
            "ocr_batch": "请检查 OCR 接口地址/Token/网络（设置→OCR API）",
            "extract": "请检查大模型 Provider/API Key/模型名（设置→病历提取 LLM）",
            "export": "请确认 Excel 模板未被占用、输出路径可写",
        }
        base = f"{type(exc).__name__}: {exc}"
        hint = hints.get(step_key)
        return f"{base}（{hint}）" if hint else base

    def _summary_text(self, summary: Dict[str, List[str]], aborted: bool) -> str:
        title_map = {s.key: s.title for s in PIPELINE_STEPS}
        ok = "、".join(title_map[k] for k in summary["success"]) or "无"
        err = "、".join(title_map[k] for k in summary["error"]) or "无"
        skip = "、".join(title_map[k] for k in summary["skipped"]) or "无"
        head = "流水线已中止" if aborted else ("流水线完成" if not summary["error"] else "流水线完成（部分步骤失败）")
        return f"{head}｜成功: {ok}｜失败: {err}｜跳过: {skip}"


class PipelineController(QObject):
    """启动/管理流水线工作线程的门面。"""

    def __init__(self):
        super().__init__()
        self.worker: Optional[PipelineWorker] = None

    def run(self, config: PipelineConfig) -> PipelineWorker:
        if self.worker:
            raise RuntimeError("流水线正在运行中")
        self.worker = PipelineWorker(config)
        self.worker.finished.connect(lambda *_: self._cleanup())
        self.worker.start()
        return self.worker

    def stop(self):
        if self.worker:
            self.worker.stop()

    def _cleanup(self):
        self.worker = None
