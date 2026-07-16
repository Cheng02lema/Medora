from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QFileDialog,
    QTextEdit,
    QComboBox,
    QDoubleSpinBox,
    QSpinBox,
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QWidget,
    QSplitter,
    QFrame,
    QSizePolicy,
    QScrollArea,
)

from typing import Optional

from ..config.manager import ConfigManager
from .base import BaseView


class PromptView(BaseView):
    start_generation = pyqtSignal(dict)

    def __init__(self, config: ConfigManager, parent=None):
        super().__init__(config, parent)
        self._build_ui()
        self.refresh_from_config()

    def _build_ui(self):
        outer_layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer_layout.addWidget(scroll)
        container = QWidget()
        scroll.setWidget(container)
        layout = QVBoxLayout(container)
        title = QLabel("提示词工程生成")
        title.setObjectName("Title")
        subtitle = QLabel("读取 Excel 模版，结合提示词 LLM 配置输出专业提示词工程。")
        subtitle.setObjectName("SubTitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        splitter = QSplitter(Qt.Horizontal)
        form_widget = QWidget()
        form_layout = QVBoxLayout(form_widget)
        form_layout.setSpacing(16)

        base_group = QGroupBox("基础参数")
        base_form = QFormLayout()
        base_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self.excel_edit = QLineEdit(self.config.get("prompt", "excel_template"))
        excel_btn = QPushButton("浏览")
        excel_btn.clicked.connect(lambda: self._choose_file(self.excel_edit, "Excel (*.xlsx *.xls)"))
        base_form.addRow("Excel 模版", self._combine(self.excel_edit, excel_btn))

        self.sheet_edit = QLineEdit()
        self.sheet_edit.setMinimumWidth(320)
        self.sheet_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        base_form.addRow("Sheet 名称", self.sheet_edit)

        self.auto_rules_edit = QLineEdit(self.config.get("prompt", "auto_rules"))
        ar_btn = QPushButton("浏览")
        ar_btn.clicked.connect(lambda: self._choose_file(self.auto_rules_edit, "YAML (*.yaml *.yml)"))
        base_form.addRow("Auto rules", self._combine(self.auto_rules_edit, ar_btn))

        self.blueprint_edit = QLineEdit(self.config.get("prompt", "blueprint"))
        bp_btn = QPushButton("浏览")
        bp_btn.clicked.connect(lambda: self._choose_file(self.blueprint_edit, "YAML (*.yaml *.yml)"))
        base_form.addRow("蓝图文件", self._combine(self.blueprint_edit, bp_btn))

        self.template_edit = QLineEdit(self.config.get("prompt", "template"))
        tpl_btn = QPushButton("浏览")
        tpl_btn.clicked.connect(lambda: self._choose_file(self.template_edit, "Jinja (*.jinja *.j2 *.md)"))
        base_form.addRow("Markdown 模版", self._combine(self.template_edit, tpl_btn))

        self.output_edit = QLineEdit(self.config.get("prompt", "output"))
        out_btn = QPushButton("保存为")
        out_btn.clicked.connect(lambda: self._choose_save(self.output_edit, "Markdown (*.md)"))
        base_form.addRow("输出文件", self._combine(self.output_edit, out_btn))

        base_group.setLayout(base_form)
        form_layout.addWidget(base_group)

        llm_group = QGroupBox("提示词 LLM API")
        llm_form = QFormLayout()
        llm_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        llm_conf = self.config.data.get("prompt_llm", {})

        self.provider_combo = QComboBox()
        self.provider_combo.addItem("仅使用规则", "")
        self.provider_combo.addItem("OpenAI 兼容 API", "openai")
        self.provider_combo.addItem("Azure OpenAI", "azure")
        self.provider_combo.addItem("DashScope", "dashscope")
        provider_value = llm_conf.get("provider", "")
        idx = self.provider_combo.findData(provider_value)
        self.provider_combo.setCurrentIndex(idx if idx >= 0 else 0)
        llm_form.addRow("Provider", self.provider_combo)

        self.model_edit = QLineEdit(llm_conf.get("model", "gpt-4o-mini"))
        llm_form.addRow("模型/部署", self.model_edit)

        self.temp_spin = QDoubleSpinBox()
        self.temp_spin.setRange(0.0, 2.0)
        self.temp_spin.setSingleStep(0.05)
        self.temp_spin.setValue(float(llm_conf.get("temperature", 0.1)))
        llm_form.addRow("Temperature", self.temp_spin)

        self.max_tokens_spin = QSpinBox()
        self.max_tokens_spin.setRange(100, 8000)
        self.max_tokens_spin.setValue(int(llm_conf.get("max_tokens", 2000)))
        llm_form.addRow("Max tokens", self.max_tokens_spin)

        self.chunk_spin = QSpinBox()
        self.chunk_spin.setRange(1, 200)
        self.chunk_spin.setValue(20)
        llm_form.addRow("分批大小", self.chunk_spin)

        self.api_key_edit = QLineEdit(self.config.get_secret("prompt_llm"))
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        llm_form.addRow("API Key", self.api_key_edit)

        self.base_url_edit = QLineEdit(llm_conf.get("base_url", ""))
        llm_form.addRow("Base URL", self.base_url_edit)

        self.dry_run_checkbox = QCheckBox("Dry run（只使用规则）")
        self.dry_run_checkbox.setChecked(True)
        llm_form.addRow(self.dry_run_checkbox)

        llm_group.setLayout(llm_form)
        form_layout.addWidget(llm_group)

        btn_layout = QHBoxLayout()
        self.generate_btn = QPushButton("生成提示词工程")
        self.generate_btn.clicked.connect(self._on_generate)
        btn_layout.addWidget(self.generate_btn)
        self.save_btn = QPushButton("保存配置")
        self.save_btn.clicked.connect(self._save_config)
        btn_layout.addWidget(self.save_btn)
        btn_layout.addStretch()
        form_layout.addLayout(btn_layout)
        form_layout.addStretch()

        splitter.addWidget(form_widget)

        log_frame = QFrame()
        log_layout = QVBoxLayout(log_frame)
        log_label = QLabel("运行日志")
        log_label.setStyleSheet("font-weight:600;")
        log_layout.addWidget(log_label)
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setObjectName("promptLog")
        log_layout.addWidget(self.log_view)

        splitter.addWidget(log_frame)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        layout.addWidget(splitter)

    def _combine(self, edit: QLineEdit, btn: QPushButton) -> QWidget:
        wrapper = QWidget()
        h = QHBoxLayout(wrapper)
        h.setContentsMargins(0, 0, 0, 0)
        edit.setMinimumWidth(360)
        edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        h.addWidget(edit)
        h.addWidget(btn)
        return wrapper

    def _choose_file(self, target: QLineEdit, file_filter: str):
        path, _ = QFileDialog.getOpenFileName(self, "选择文件", filter=file_filter)
        if path:
            target.setText(path)

    def _choose_save(self, target: QLineEdit, file_filter: str):
        path, _ = QFileDialog.getSaveFileName(self, "保存文件", filter=file_filter)
        if path:
            target.setText(path)

    def _on_generate(self):
        payload = {
            "excel": self.excel_edit.text().strip(),
            "sheet": self.sheet_edit.text().strip() or None,
            "auto_rules": self.auto_rules_edit.text().strip(),
            "blueprint": self.blueprint_edit.text().strip(),
            "template": self.template_edit.text().strip(),
            "output": self.output_edit.text().strip(),
            "llm_provider": self.provider_combo.currentData(),
            "model": self.model_edit.text().strip(),
            "temperature": self.temp_spin.value(),
            "max_tokens": self.max_tokens_spin.value(),
            "chunk_size": self.chunk_spin.value(),
            "api_key": self.api_key_edit.text().strip() or None,
            "base_url": self.base_url_edit.text().strip() or None,
            "deployment": None,
            "api_version": None,
            "dry_run": self.dry_run_checkbox.isChecked(),
        }
        self.start_generation.emit(payload)

    def set_running(self, running: bool):
        self.generate_btn.setEnabled(not running)

    def append_log(self, text: str):
        self.log_view.append(text)

    def _save_config(self):
        self.config.update_section("prompt", {
            "excel_template": self.excel_edit.text().strip(),
            "auto_rules": self.auto_rules_edit.text().strip(),
            "blueprint": self.blueprint_edit.text().strip(),
            "template": self.template_edit.text().strip(),
            "output": self.output_edit.text().strip(),
        })
        self.config.update_section("prompt_llm", {
            "provider": self.provider_combo.currentData(),
            "model": self.model_edit.text().strip(),
            "temperature": self.temp_spin.value(),
            "max_tokens": self.max_tokens_spin.value(),
            "base_url": self.base_url_edit.text().strip(),
        })
        self.config.set_secret("prompt_llm", self.api_key_edit.text().strip())
        self.append_log("配置已保存")

    def refresh_from_config(self, section: Optional[str] = None):
        prompt_conf = self.config.data.get("prompt", {})
        if section in (None, "prompt"):
            self.excel_edit.setText(prompt_conf.get("excel_template", self.excel_edit.text()))
            self.auto_rules_edit.setText(prompt_conf.get("auto_rules", self.auto_rules_edit.text()))
            self.blueprint_edit.setText(prompt_conf.get("blueprint", self.blueprint_edit.text()))
            self.template_edit.setText(prompt_conf.get("template", self.template_edit.text()))
            self.output_edit.setText(prompt_conf.get("output", self.output_edit.text()))
        prompt_llm = self.config.data.get("prompt_llm", {})
        if section in (None, "prompt_llm"):
            provider_value = prompt_llm.get("provider", "")
            idx = self.provider_combo.findData(provider_value)
            if idx >= 0:
                self.provider_combo.setCurrentIndex(idx)
            self.model_edit.setText(prompt_llm.get("model", self.model_edit.text()))
            self.temp_spin.setValue(float(prompt_llm.get("temperature", self.temp_spin.value())))
            self.max_tokens_spin.setValue(int(prompt_llm.get("max_tokens", self.max_tokens_spin.value())))
            self.api_key_edit.setText(self.config.get_secret("prompt_llm"))
            self.base_url_edit.setText(prompt_llm.get("base_url", ""))
