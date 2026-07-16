from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Dict, List, Optional

from PyQt5.QtCore import QObject, QThread, pyqtSignal

from promptforge.cli import build_sections, enrich_with_llm, load_blueprint
from promptforge.excel_parser import ExcelReader
from promptforge.template_renderer import TemplateRenderer
from promptforge.variable_loader import AutoRuleEngine, VariableLoader


ENCODING_CANDIDATES = ("utf-8", "utf-8-sig", "gbk", "gb2312", "big5", "cp936", "latin-1")


@dataclass
class PromptTask:
    excel: str
    sheet: Optional[str]
    auto_rules: str
    blueprint: str
    template: str
    output: str
    llm_provider: str = ""
    model: str = "gpt-4o-mini"
    temperature: float = 0.1
    max_tokens: int = 2000
    chunk_size: int = 20
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    deployment: Optional[str] = None
    api_version: Optional[str] = None
    dry_run: bool = True
    extraction_template: Optional[str] = None


def _ensure_utf8_file(path: str, temp_files: List[str]) -> str:
    file_path = Path(path)
    data = file_path.read_bytes()
    for encoding in ENCODING_CANDIDATES:
        try:
            text = data.decode(encoding)
            if encoding in ("utf-8", "utf-8-sig"):
                return str(file_path)
            tmp = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=file_path.suffix)
            tmp.write(text)
            tmp.flush()
            tmp.close()
            temp_files.append(tmp.name)
            return tmp.name
        except UnicodeDecodeError:
            continue
    # fallback to utf-8 replace, ensuring file can still be parsed
    text = data.decode("utf-8", errors="replace")
    tmp = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=file_path.suffix)
    tmp.write(text)
    tmp.flush()
    tmp.close()
    temp_files.append(tmp.name)
    return tmp.name


def generate_prompt_document(task: PromptTask, notifier: Optional[Callable[[str], None]] = None) -> Path:
    """执行核心提示词生成逻辑，可被多处调用"""

    def emit(msg: str):
        if notifier:
            notifier(msg)

    temp_files: List[str] = []
    try:
        excel_path = task.excel
        auto_rules_path = _ensure_utf8_file(task.auto_rules, temp_files)
        blueprint_path = _ensure_utf8_file(task.blueprint, temp_files)
        template_path = Path(_ensure_utf8_file(task.template, temp_files))

        emit("读取 Excel 模版…")
        reader = ExcelReader(excel_path)
        rows = reader.read(task.sheet)

        emit("加载 auto-rules 配置…")
        auto_rules = AutoRuleEngine(auto_rules_path)
        loader = VariableLoader(auto_rules)
        variables = loader.load(rows)
        emit(f"共加载 {len(variables)} 个字段")

        emit("加载蓝图与模板…")
        blueprint = load_blueprint(blueprint_path)
        renderer = TemplateRenderer(template_path.parent)

        args = SimpleNamespace(
            dry_run=task.dry_run,
            llm_provider=task.llm_provider or None,
            model=task.model,
            temperature=task.temperature,
            max_tokens=task.max_tokens,
            chunk_size=task.chunk_size,
            base_url=task.base_url,
            api_key=task.api_key,
            deployment=task.deployment,
            api_version=task.api_version,
        )

        if task.llm_provider and not task.dry_run:
            emit(f"调用 {task.llm_provider} API 进行增强…")
            enrich_with_llm(variables, task.llm_provider, blueprint, args)

        emit("渲染提示词工程…")
        sections = build_sections(variables, blueprint)
        result_text = renderer.render(
            template_path.name,
            {
                "project": blueprint.get("project", {}),
                "blueprint": blueprint,
                "variable_sections": sections,
                "total_variables": len(variables),
                "extraction_template": task.extraction_template,
                "extraction_template_name": Path(task.extraction_template).name if task.extraction_template else "",
            },
        )

        output_path = Path(task.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(result_text, encoding="utf-8")
        return output_path
    finally:
        for temp_path in temp_files:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


class PromptGenerationWorker(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(self, task: PromptTask):
        super().__init__()
        self.task = task

    def run(self):
        try:
            output_path = generate_prompt_document(self.task, self.progress.emit)
            self.finished.emit(True, f"提示词工程已生成：{output_path}")
        except Exception as exc:
            self.finished.emit(False, f"生成失败：{exc}")


class PromptController(QObject):
    """协调 PromptGenerationWorker 的生命周期"""

    def __init__(self):
        super().__init__()
        self.worker: Optional[PromptGenerationWorker] = None

    def start(self, task_data: Dict) -> PromptGenerationWorker:
        if self.worker:
            raise RuntimeError("当前任务尚未结束")
        task = PromptTask(**task_data)
        self.worker = PromptGenerationWorker(task)
        self.worker.finished.connect(lambda *_: self._cleanup_worker())
        self.worker.start()
        return self.worker

    def _cleanup_worker(self):
        self.worker = None
