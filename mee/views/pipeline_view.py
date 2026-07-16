from typing import Dict, List, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QWidget,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QFileDialog,
    QLineEdit,
    QTextEdit,
    QComboBox,
    QGroupBox,
    QFormLayout,
    QCheckBox,
    QMessageBox,
    QSplitter,
    QFrame,
    QSizePolicy,
    QScrollArea,
    qApp,
)

from ..config.manager import ConfigManager
from ..controllers.pipeline_controller import PIPELINE_STEPS, PipelineStep
from ..modules.ocr_client import DEFAULT_OCR_MODEL
from ..modules.ocr_presets import DEFAULT_OCR_PRESET, get_ocr_preset_options
from .base import BaseView


class StepWidget(QWidget):
    ICON_PATHS = {
        "pending": ":/icons/status_warning.svg",
        "running": ":/icons/status_warning.svg",
        "success": ":/icons/status_success.svg",
        "warning": ":/icons/status_warning.svg",
        "error": ":/icons/status_error.svg",
        "skipped": ":/icons/status_warning.svg",
    }
    ICON_CACHE: Dict[str, QPixmap] = {}

    def __init__(self, index: int, step: PipelineStep):
        super().__init__()
        self.step = step
        self._current_state = "pending"
        self._current_tooltip = ""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(16)

        self.checkbox = QCheckBox()
        self.checkbox.setChecked(True)
        layout.addWidget(self.checkbox)

        badge = QLabel(f"{index}")
        badge.setObjectName("StepBadge")
        layout.addWidget(badge)

        text_layout = QVBoxLayout()
        self.title_label = QLabel()
        self.desc_label = QLabel()
        self.desc_label.setWordWrap(True)
        self.desc_label.setObjectName("StatusSmall")
        text_layout.addWidget(self.title_label)
        text_layout.addWidget(self.desc_label)
        layout.addLayout(text_layout)

        status_layout = QHBoxLayout()
        status_layout.setSpacing(6)
        status_layout.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.status_icon = QLabel()
        self.status_icon.setFixedSize(20, 20)
        self.status = QLabel()
        self.status.setObjectName("StepStatus")
        self.status.setProperty("pending", True)
        status_layout.addWidget(self.status_icon)
        status_layout.addWidget(self.status)
        layout.addLayout(status_layout)
        layout.addStretch()
        self.translator_manager = qApp.property("translator_manager")
        if self.translator_manager:
            self.translator_manager.languageChanged.connect(lambda _: self._apply_translation())
        self._apply_translation()
        self.set_status(self.tr("Pending"), "pending")

    def set_status(self, text: str, state: str = "pending", tooltip: Optional[str] = None):
        self.status.setText(text)
        self.status.setProperty("pending", state == "pending")
        self.status.setProperty("status", state)
        self._current_tooltip = tooltip or ""
        self.status.setToolTip(self._current_tooltip)
        self._current_state = state
        pixmap = self._resolve_icon(state)
        self.status_icon.setPixmap(pixmap.scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self._refresh_status_style()

    def _resolve_icon(self, state: str) -> QPixmap:
        key = state if state in self.ICON_PATHS else "pending"
        if key not in self.ICON_CACHE:
            self.ICON_CACHE[key] = QPixmap(self.ICON_PATHS[key])
        return self.ICON_CACHE[key]

    def _refresh_status_style(self):
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self.status.update()

    def is_checked(self) -> bool:
        return self.checkbox.isChecked()

    def set_checked(self, value: bool):
        self.checkbox.setChecked(value)

    def _apply_translation(self):
        self.title_label.setText(self.tr(self.step.title))
        optional = f" ({self.tr('Optional')})" if self.step.optional else ""
        self.desc_label.setText(self.tr(self.step.description) + optional)


class PipelineView(BaseView):
    start_pipeline = pyqtSignal(dict)
    stop_pipeline = pyqtSignal()

    def __init__(self, config: ConfigManager, parent=None):
        super().__init__(config, parent)
        self.step_widgets: Dict[str, StepWidget] = {}
        self._build_ui()

    def _build_ui(self):
        self.step_states: Dict[str, str] = {}
        self.step_messages: Dict[str, str] = {}
        self.state_texts: Dict[str, str] = {}
        self.scenario_labels: Dict[str, QLabel] = {}
        self.ocr_labels: Dict[str, QLabel] = {}
        self.extra_labels: Dict[str, QLabel] = {}

        outer_layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer_layout.addWidget(scroll)
        container = QWidget()
        scroll.setWidget(container)
        main_layout = QVBoxLayout(container)
        self.title_label = QLabel()
        self.title_label.setObjectName("Title")
        self.subtitle_label = QLabel()
        self.subtitle_label.setObjectName("SubTitle")
        main_layout.addWidget(self.title_label)
        main_layout.addWidget(self.subtitle_label)

        splitter = QSplitter(Qt.Horizontal)
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setSpacing(14)

        self.scenario_group = QGroupBox()
        scenario_form = QFormLayout()
        scenario_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self.scenario_combo = QComboBox()
        self.scenario_options = [
            ("图片病历", "image"),
            ("PDF 病历", "pdf"),
            ("文本病历", "text"),
        ]
        scenario_form.addRow(self._create_form_label(self.scenario_labels, "type"), self.scenario_combo)

        self.input_edit = QLineEdit()
        self.input_btn = QPushButton(self.tr("Browse"))
        self.input_btn.clicked.connect(lambda: self._choose_dir(self.input_edit))
        scenario_form.addRow(self._create_form_label(self.scenario_labels, "input"), self._combine(self.input_edit, self.input_btn))

        self.preprocess_edit = QLineEdit(self.config.get("pipeline", "preprocess_output", "output/preprocess"))
        self.pre_btn = QPushButton(self.tr("Browse"))
        self.pre_btn.clicked.connect(lambda: self._choose_dir(self.preprocess_edit))
        scenario_form.addRow(self._create_form_label(self.scenario_labels, "preprocess"), self._combine(self.preprocess_edit, self.pre_btn))

        self.ocr_output_edit = QLineEdit(self.config.get("pipeline", "ocr_output", "output/ocr"))
        self.ocr_btn = QPushButton(self.tr("Browse"))
        self.ocr_btn.clicked.connect(lambda: self._choose_dir(self.ocr_output_edit))
        scenario_form.addRow(self._create_form_label(self.scenario_labels, "ocr_output"), self._combine(self.ocr_output_edit, self.ocr_btn))

        self.cleanup_edit = QLineEdit(self.config.get("pipeline", "cleanup_target", "output/ocr"))
        self.cleanup_btn = QPushButton(self.tr("Browse"))
        self.cleanup_btn.clicked.connect(lambda: self._choose_dir(self.cleanup_edit))
        scenario_form.addRow(self._create_form_label(self.scenario_labels, "cleanup"), self._combine(self.cleanup_edit, self.cleanup_btn))

        self.template_edit = QLineEdit(self.config.get("pipeline", "extraction_template", ""))
        self._expand_line(self.template_edit, width=420)
        self.template_btn = QPushButton(self.tr("Browse"))
        self.template_btn.clicked.connect(lambda: self._choose_file(self.template_edit, self.tr("模板文件 (*.xlsx *.xls *.json)")))
        scenario_form.addRow(self._create_form_label(self.scenario_labels, "template"), self._combine(self.template_edit, self.template_btn))

        self.output_edit = QLineEdit(self.config.get("pipeline", "output_excel", ""))
        self._expand_line(self.output_edit, width=420)
        self.output_btn = QPushButton(self.tr("Browse"))
        self.output_btn.clicked.connect(lambda: self._choose_save(self.output_edit, self.tr("Excel files (*.xlsx)")))
        scenario_form.addRow(self._create_form_label(self.scenario_labels, "output"), self._combine(self.output_edit, self.output_btn))
        self.scenario_group.setLayout(scenario_form)
        left_layout.addWidget(self.scenario_group)

        ocr_config = self.config.data.get("ocr_api", {})
        self.ocr_group = QGroupBox()
        ocr_form = QFormLayout()
        ocr_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.api_url_edit = QLineEdit(ocr_config.get("url", ""))
        self.api_token_edit = QLineEdit(self.config.get_secret("ocr_api"))
        self.api_token_edit.setEchoMode(QLineEdit.Password)
        self.ocr_model_edit = QLineEdit(ocr_config.get("model", DEFAULT_OCR_MODEL))
        self.ocr_preset_combo = QComboBox()
        for label, value in get_ocr_preset_options():
            self.ocr_preset_combo.addItem(label, value)
        self._set_combo_data(self.ocr_preset_combo, ocr_config.get("preset", DEFAULT_OCR_PRESET))
        self._expand_line(self.api_url_edit)
        self._expand_line(self.api_token_edit)
        self._expand_line(self.ocr_model_edit)
        ocr_form.addRow(self._create_form_label(self.ocr_labels, "api_url"), self.api_url_edit)
        ocr_form.addRow(self._create_form_label(self.ocr_labels, "api_token"), self.api_token_edit)
        ocr_form.addRow(self._create_form_label(self.ocr_labels, "ocr_model"), self.ocr_model_edit)
        ocr_form.addRow(self._create_form_label(self.ocr_labels, "ocr_preset"), self.ocr_preset_combo)
        self.file_ext_edit = QLineEdit(self.config.get("pipeline", "file_extensions", ".jpg,.jpeg,.png,.pdf"))
        self._expand_line(self.file_ext_edit)
        ocr_form.addRow(self._create_form_label(self.ocr_labels, "file_ext"), self.file_ext_edit)
        self.save_api_btn = QPushButton()
        self.save_api_btn.clicked.connect(self._save_ocr_settings)
        ocr_form.addRow(self.save_api_btn)
        self.ocr_group.setLayout(ocr_form)
        left_layout.addWidget(self.ocr_group)

        self.extras_group = QGroupBox()
        extras_form = QFormLayout()
        extras_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.payment_checkbox = QCheckBox()
        self.payment_checkbox.setChecked(True)
        extras_form.addRow(self.payment_checkbox)
        self.payment_pattern_edit = QLineEdit(self.config.get("pipeline", "payment_pattern", "-缴费情况.jpg"))
        self._expand_line(self.payment_pattern_edit)
        extras_form.addRow(self._create_form_label(self.extra_labels, "payment_pattern"), self.payment_pattern_edit)
        self.cleanup_pattern_edit = QLineEdit(self.config.get("pipeline", "cleanup_pattern", "*右表格_0.md"))
        self._expand_line(self.cleanup_pattern_edit)
        extras_form.addRow(self._create_form_label(self.extra_labels, "cleanup_pattern"), self.cleanup_pattern_edit)
        self.extras_group.setLayout(extras_form)
        left_layout.addWidget(self.extras_group)

        control_layout = QHBoxLayout()
        self.start_btn = QPushButton()
        self.start_btn.clicked.connect(self._on_start)
        self.start_btn.setAccessibleName("pipelineStartButton")
        control_layout.addWidget(self.start_btn)
        self.stop_btn = QPushButton()
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop)
        self.stop_btn.setAccessibleName("pipelineStopButton")
        control_layout.addWidget(self.stop_btn)
        self.clear_btn = QPushButton()
        self.clear_btn.clicked.connect(lambda: self.log_view.clear())
        control_layout.addWidget(self.clear_btn)
        control_layout.addStretch()
        left_layout.addLayout(control_layout)
        left_layout.addStretch()

        splitter.addWidget(left_panel)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setSpacing(12)

        steps_frame = QFrame()
        steps_layout = QVBoxLayout(steps_frame)
        self.steps_label = QLabel()
        self.steps_label.setObjectName("SectionHeading")
        steps_layout.addWidget(self.steps_label)
        self.step_list = QListWidget()
        for idx, step in enumerate(PIPELINE_STEPS, start=1):
            widget = StepWidget(idx, step)
            item = QListWidgetItem()
            item.setSizeHint(widget.sizeHint())
            self.step_list.addItem(item)
            self.step_list.setItemWidget(item, widget)
            self.step_widgets[step.key] = widget
            self.step_states[step.key] = "pending"
            self.step_messages[step.key] = ""
        steps_layout.addWidget(self.step_list)
        right_layout.addWidget(steps_frame)

        log_frame = QFrame()
        log_layout = QVBoxLayout(log_frame)
        self.log_title = QLabel()
        self.log_title.setObjectName("SectionHeading")
        log_layout.addWidget(self.log_title)
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setObjectName("pipelineLog")
        self.log_view.setAccessibleName("pipelineLog")
        log_layout.addWidget(self.log_view)
        right_layout.addWidget(log_frame)

        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 4)

        main_layout.addWidget(splitter)
        self.scenario_defaults = {
            "image": {"preprocess": True, "slice": True, "ocr_batch": True, "ocr_payment": True, "merge": True, "extract": True, "export": True, "cleanup": True},
            "pdf": {"preprocess": False, "slice": True, "ocr_batch": True, "ocr_payment": True, "merge": True, "extract": True, "export": True, "cleanup": True},
            "text": {"preprocess": False, "slice": False, "ocr_batch": False, "ocr_payment": False, "merge": False, "extract": True, "export": True, "cleanup": False},
        }
        self._populate_scenarios()
        self.refresh_from_config()
        self.scenario_combo.currentIndexChanged.connect(self._apply_scenario_defaults)
        self._apply_scenario_defaults()
        self.retranslate()

    def _create_form_label(self, store: Dict[str, QLabel], key: str) -> QLabel:
        label = QLabel()
        store[key] = label
        return label

    def _combine(self, edit: QLineEdit, btn: QPushButton) -> QWidget:
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        edit.setMinimumWidth(420)
        edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(edit)
        if btn.text():
            layout.addWidget(btn)
        return wrapper

    def _expand_line(self, edit: QLineEdit, width: int = 380):
        edit.setMinimumWidth(width)
        edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def _choose_dir(self, target: QLineEdit):
        path = QFileDialog.getExistingDirectory(self, self.tr("Select folder"))
        if path:
            target.setText(path)

    def _choose_file(self, target: QLineEdit, file_filter: str):
        path, _ = QFileDialog.getOpenFileName(self, self.tr("Select file"), filter=file_filter)
        if path:
            target.setText(path)

    def _choose_save(self, target: QLineEdit, file_filter: str):
        path, _ = QFileDialog.getSaveFileName(self, self.tr("Select file"), filter=file_filter)
        if path:
            target.setText(path)

    def _on_start(self):
        params = {
            "scenario": self.scenario_combo.currentData(),
            "raw_input": self.input_edit.text().strip(),
            "preprocess_output": self.preprocess_edit.text().strip(),
            "ocr_output": self.ocr_output_edit.text().strip(),
            "api_url": self.api_url_edit.text().strip(),
            "api_token": self.api_token_edit.text().strip(),
            "ocr_model": self.ocr_model_edit.text().strip() or DEFAULT_OCR_MODEL,
            "ocr_preset": self.ocr_preset_combo.currentData() or DEFAULT_OCR_PRESET,
            "file_extensions": [ext.strip() for ext in self.file_ext_edit.text().split(",") if ext.strip()],
            "enable_payment_ocr": self.payment_checkbox.isChecked(),
            "payment_pattern": self.payment_pattern_edit.text().strip(),
            "cleanup_target": self.cleanup_edit.text().strip(),
            "cleanup_pattern": self.cleanup_pattern_edit.text().strip(),
            "extraction_template": self.template_edit.text().strip(),
            "output_excel": self.output_edit.text().strip(),
        }
        if params["scenario"] != "text" and not params["raw_input"]:
            QMessageBox.warning(self, self.tr("Missing parameter"), self.tr("Please select the raw input directory."))
            return
        selected = [key for key, widget in self.step_widgets.items() if widget.is_checked()]
        if not selected:
            QMessageBox.warning(self, self.tr("Nothing selected"), self.tr("Select at least one step to run."))
            return
        params["selected_steps"] = selected
        self._persist_pipeline_settings()
        self.start_pipeline.emit(params)

    def update_step_status(self, step_key: str, text: str, state: str = "pending"):
        widget = self.step_widgets.get(step_key)
        if widget:
            self.step_states[step_key] = state
            self.step_messages[step_key] = text
            widget.set_status(self._state_text(state), state, text)

    def append_log(self, message: str):
        self.log_view.append(message)

    def set_running(self, running: bool):
        self.start_btn.setEnabled(not running)
        self.stop_btn.setEnabled(running)

    def _on_stop(self):
        self.stop_btn.setEnabled(False)
        self.append_log(self.tr("正在停止…"))
        self.stop_pipeline.emit()

    def on_pipeline_finished(self):
        self.stop_btn.setEnabled(False)

    def _save_ocr_settings(self):
        self.config.update_section("ocr_api", {
            "url": self.api_url_edit.text().strip(),
            "model": self.ocr_model_edit.text().strip() or DEFAULT_OCR_MODEL,
            "preset": self.ocr_preset_combo.currentData() or DEFAULT_OCR_PRESET,
        })
        self.config.set_secret("ocr_api", self.api_token_edit.text().strip())
        self.config.update_section("pipeline", {
            "file_extensions": self.file_ext_edit.text().strip(),
        })
        self.append_log(self.tr("OCR settings saved"))

    def _persist_pipeline_settings(self):
        self.config.update_section("pipeline", {
            "raw_input": self.input_edit.text().strip(),
            "preprocess_output": self.preprocess_edit.text().strip(),
            "ocr_output": self.ocr_output_edit.text().strip(),
            "cleanup_target": self.cleanup_edit.text().strip(),
            "file_extensions": self.file_ext_edit.text().strip(),
            "payment_pattern": self.payment_pattern_edit.text().strip(),
            "cleanup_pattern": self.cleanup_pattern_edit.text().strip(),
            "extraction_template": self.template_edit.text().strip(),
            "output_excel": self.output_edit.text().strip(),
        })

    def _apply_scenario_defaults(self):
        scenario = self.scenario_combo.currentData()
        defaults = self.scenario_defaults.get(scenario, {})
        for key, widget in self.step_widgets.items():
            if key in defaults:
                widget.set_checked(defaults[key])
        # ensure statuses reflect scenario change (no translation needed here)

    def refresh_from_config(self, section: Optional[str] = None):
        pipeline_conf = self.config.data.get("pipeline", {})
        if section in (None, "pipeline"):
            self.input_edit.setText(pipeline_conf.get("raw_input", ""))
            self.preprocess_edit.setText(pipeline_conf.get("preprocess_output", ""))
            self.ocr_output_edit.setText(pipeline_conf.get("ocr_output", ""))
            self.cleanup_edit.setText(pipeline_conf.get("cleanup_target", ""))
            self.file_ext_edit.setText(pipeline_conf.get("file_extensions", ".jpg,.jpeg,.png,.pdf"))
            self.payment_pattern_edit.setText(pipeline_conf.get("payment_pattern", "-缴费情况.jpg"))
            self.cleanup_pattern_edit.setText(pipeline_conf.get("cleanup_pattern", "*右表格_0.md"))
            self.template_edit.setText(pipeline_conf.get("extraction_template", ""))
            self.output_edit.setText(pipeline_conf.get("output_excel", ""))
        if section in (None, "ocr_api"):
            ocr_conf = self.config.data.get("ocr_api", {})
            self.api_url_edit.setText(ocr_conf.get("url", ""))
            self.api_token_edit.setText(self.config.get_secret("ocr_api"))
            self.ocr_model_edit.setText(ocr_conf.get("model", DEFAULT_OCR_MODEL))
            self._set_combo_data(self.ocr_preset_combo, ocr_conf.get("preset", DEFAULT_OCR_PRESET))

    def retranslate(self):
        self.title_label.setText(self.tr("Medical Record Pipeline"))
        self.subtitle_label.setText(self.tr("Chain preprocessing, OCR, prompting, and LLM extraction for different input sources."))
        self.scenario_group.setTitle(self.tr("Scenario & Directories"))
        self.ocr_group.setTitle(self.tr("OCR API Settings"))
        self.extras_group.setTitle(self.tr("Additional Options"))

        for key, text in [
            ("type", self.tr("Processing type")),
            ("input", self.tr("Raw input directory")),
            ("preprocess", self.tr("Preprocess output")),
            ("ocr_output", self.tr("OCR output")),
            ("cleanup", self.tr("Cleanup directory")),
            ("template", self.tr("抽取模板 (Excel/JSON)")),
            ("output", self.tr("结果 Excel 输出")),
        ]:
            label = self.scenario_labels.get(key)
            if label:
                label.setText(text)

        for key, text in [
            ("api_url", self.tr("API URL")),
            ("api_token", self.tr("API token")),
            ("ocr_model", self.tr("OCR model")),
            ("ocr_preset", self.tr("OCR preset")),
            ("file_ext", self.tr("File extensions to OCR")),
        ]:
            label = self.ocr_labels.get(key)
            if label:
                label.setText(text)

        for key, text in [
            ("payment_pattern", self.tr("Payment suffix pattern")),
            ("cleanup_pattern", self.tr("Cleanup glob pattern")),
        ]:
            label = self.extra_labels.get(key)
            if label:
                label.setText(text)

        self.input_btn.setText(self.tr("Browse"))
        self.pre_btn.setText(self.tr("Browse"))
        self.ocr_btn.setText(self.tr("Browse"))
        self.cleanup_btn.setText(self.tr("Browse"))
        self.template_btn.setText(self.tr("Browse"))
        self.output_btn.setText(self.tr("Browse"))
        self.save_api_btn.setText(self.tr("Save OCR settings"))
        self.payment_checkbox.setText(self.tr("对缴费单据图片单独补救识别"))
        self.start_btn.setText(self.tr("开始自动流水线"))
        self.stop_btn.setText(self.tr("停止"))
        self.clear_btn.setText(self.tr("清空日志"))
        self.steps_label.setText(self.tr("Pipeline steps"))
        self.log_title.setText(self.tr("Execution log"))

        self._populate_scenarios()
        self._refresh_state_texts()
        for key, widget in self.step_widgets.items():
            state = self.step_states.get(key, "pending")
            message = self.step_messages.get(key, "")
            widget.set_status(self._state_text(state), state, message or None)

    def _populate_scenarios(self):
        current = self.scenario_combo.currentData()
        self.scenario_combo.blockSignals(True)
        self.scenario_combo.clear()
        for label, value in self.scenario_options:
            self.scenario_combo.addItem(self.tr(label), value)
        index = self.scenario_combo.findData(current)
        self.scenario_combo.setCurrentIndex(index if index >= 0 else 0)
        self.scenario_combo.blockSignals(False)

    def _set_combo_data(self, combo: QComboBox, value: str):
        index = combo.findData(value)
        combo.setCurrentIndex(index if index >= 0 else 0)

    def _refresh_state_texts(self):
        self.state_texts = {
            "pending": self.tr("Pending"),
            "running": self.tr("Running"),
            "success": self.tr("Completed"),
            "warning": self.tr("Manual"),
            "error": self.tr("Failed"),
            "skipped": self.tr("Skipped"),
        }

    def _state_text(self, state: str) -> str:
        return self.state_texts.get(state, self.tr("Pending"))
