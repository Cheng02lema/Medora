import tempfile
from pathlib import Path

from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtWidgets import (
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QFormLayout,
    QGroupBox,
    QDoubleSpinBox,
    QSpinBox,
    QSizePolicy,
    QMessageBox,
    QWidget,
    QHBoxLayout,
    QScrollArea,
    QComboBox,
)

from ..config.manager import ConfigManager
from ..modules.ocr_client import AsyncOCRClient, DEFAULT_OCR_MODEL
from ..modules.ocr_presets import DEFAULT_OCR_PRESET, get_ocr_preset_options
from .base import BaseView


class SettingsView(BaseView):
    settings_updated = pyqtSignal(str)
    def __init__(self, config: ConfigManager, parent=None):
        super().__init__(config, parent)
        self._build_ui()

    def _build_ui(self):
        outer_layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer_layout.addWidget(scroll)
        container = QWidget()
        scroll.setWidget(container)
        layout = QVBoxLayout(container)
        title = QLabel("系统设置")
        title.setObjectName("Title")
        subtitle = QLabel("集中管理 OCR API、提示词 LLM、病历提取 LLM 的接口信息。")
        subtitle.setObjectName("SubTitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        # OCR section
        ocr_group = QGroupBox("OCR API")
        ocr_form = QFormLayout()
        ocr_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        ocr_conf = self.config.data.get("ocr_api", {})
        self.ocr_url_edit = QLineEdit(ocr_conf.get("url", ""))
        self.ocr_url_edit.setMinimumWidth(360)
        self.ocr_url_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.ocr_token_edit = QLineEdit(self.config.get_secret("ocr_api"))
        self.ocr_token_edit.setEchoMode(QLineEdit.Password)
        self.ocr_token_edit.setMinimumWidth(360)
        self.ocr_model_edit = QLineEdit(ocr_conf.get("model", DEFAULT_OCR_MODEL))
        self.ocr_model_edit.setMinimumWidth(360)
        self.ocr_preset_combo = QComboBox()
        for label, value in get_ocr_preset_options():
            self.ocr_preset_combo.addItem(label, value)
        self._set_combo_data(self.ocr_preset_combo, ocr_conf.get("preset", DEFAULT_OCR_PRESET))
        ocr_form.addRow("接口地址", self.ocr_url_edit)
        ocr_form.addRow("Token", self.ocr_token_edit)
        ocr_form.addRow("模型", self.ocr_model_edit)
        ocr_form.addRow("预设", self.ocr_preset_combo)
        save_ocr = QPushButton("保存 OCR API")
        save_ocr.clicked.connect(self._save_ocr)
        test_ocr = QPushButton("测试 OCR API")
        test_ocr.clicked.connect(self._test_ocr_api)
        btn_row = QWidget()
        row_layout = QHBoxLayout(btn_row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(save_ocr)
        row_layout.addWidget(test_ocr)
        row_layout.addStretch()
        ocr_form.addRow(row_layout)
        ocr_group.setLayout(ocr_form)
        layout.addWidget(ocr_group)

        # Prompt LLM
        prompt_group = QGroupBox("提示词工程 LLM")
        prompt_form = QFormLayout()
        prompt_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        prompt_conf = self.config.data.get("prompt_llm", {})
        self.prompt_provider_edit = QLineEdit(prompt_conf.get("provider", ""))
        self._expand_line(self.prompt_provider_edit)
        self.prompt_base_url_edit = QLineEdit(prompt_conf.get("base_url", ""))
        self._expand_line(self.prompt_base_url_edit)
        self.prompt_api_key_edit = QLineEdit(self.config.get_secret("prompt_llm"))
        self.prompt_api_key_edit.setEchoMode(QLineEdit.Password)
        self._expand_line(self.prompt_api_key_edit)
        self.prompt_model_edit = QLineEdit(prompt_conf.get("model", "gpt-4o-mini"))
        self._expand_line(self.prompt_model_edit)
        self.prompt_temp_spin = QDoubleSpinBox()
        self.prompt_temp_spin.setRange(0.0, 2.0)
        self.prompt_temp_spin.setSingleStep(0.05)
        self.prompt_temp_spin.setValue(float(prompt_conf.get("temperature", 0.1)))
        self.prompt_max_tokens_spin = QSpinBox()
        self.prompt_max_tokens_spin.setRange(100, 8000)
        self.prompt_max_tokens_spin.setValue(int(prompt_conf.get("max_tokens", 2000)))
        prompt_form.addRow("Provider", self.prompt_provider_edit)
        prompt_form.addRow("Base URL", self.prompt_base_url_edit)
        prompt_form.addRow("API Key", self.prompt_api_key_edit)
        prompt_form.addRow("模型", self.prompt_model_edit)
        prompt_form.addRow("Temperature", self.prompt_temp_spin)
        prompt_form.addRow("Max tokens", self.prompt_max_tokens_spin)
        save_prompt = QPushButton("保存提示词 LLM")
        save_prompt.clicked.connect(self._save_prompt_llm)
        prompt_form.addRow(save_prompt)
        prompt_group.setLayout(prompt_form)
        layout.addWidget(prompt_group)

        # Extraction LLM
        extract_group = QGroupBox("病历提取 LLM / Agent")
        extract_form = QFormLayout()
        extract_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        extract_conf = self.config.data.get("extract_llm", {})
        self.extract_provider_combo = QComboBox()
        for name in ("DeepSeek", "OpenAI", "Claude", "智谱AI", "通义千问", "Azure", "自定义"):
            self.extract_provider_combo.addItem(name, name)
        self._set_combo_data(self.extract_provider_combo, extract_conf.get("provider", "DeepSeek"))
        self.extract_base_url_edit = QLineEdit(extract_conf.get("base_url", ""))
        self.extract_base_url_edit.setPlaceholderText(self.tr("留空则使用所选 Provider 的默认地址"))
        self._expand_line(self.extract_base_url_edit)
        self.extract_api_key_edit = QLineEdit(self.config.get_secret("extract_llm"))
        self.extract_api_key_edit.setEchoMode(QLineEdit.Password)
        self._expand_line(self.extract_api_key_edit)
        self.extract_model_edit = QLineEdit(extract_conf.get("model", "gpt-4o-mini"))
        self._expand_line(self.extract_model_edit)
        self.extract_temp_spin = QDoubleSpinBox()
        self.extract_temp_spin.setRange(0.0, 2.0)
        self.extract_temp_spin.setSingleStep(0.05)
        self.extract_temp_spin.setValue(float(extract_conf.get("temperature", 0.1)))
        self.extract_max_tokens_spin = QSpinBox()
        self.extract_max_tokens_spin.setRange(100, 8000)
        self.extract_max_tokens_spin.setValue(int(extract_conf.get("max_tokens", 2000)))
        extract_form.addRow("Provider", self.extract_provider_combo)
        extract_form.addRow("Base URL", self.extract_base_url_edit)
        extract_form.addRow("API Key", self.extract_api_key_edit)
        extract_form.addRow("模型", self.extract_model_edit)
        extract_form.addRow("Temperature", self.extract_temp_spin)
        extract_form.addRow("Max tokens", self.extract_max_tokens_spin)
        save_extract = QPushButton("保存提取 LLM")
        save_extract.clicked.connect(self._save_extract_llm)
        extract_form.addRow(save_extract)
        extract_group.setLayout(extract_form)
        layout.addWidget(extract_group)

        layout.addStretch()

    def _expand_line(self, line_edit: QLineEdit):
        line_edit.setMinimumWidth(360)
        line_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def _save_ocr(self):
        self.config.update_section("ocr_api", {
            "url": self.ocr_url_edit.text().strip(),
            "model": self.ocr_model_edit.text().strip() or DEFAULT_OCR_MODEL,
            "preset": self.ocr_preset_combo.currentData() or DEFAULT_OCR_PRESET,
        })
        self.config.set_secret("ocr_api", self.ocr_token_edit.text().strip())
        self._notify_saved("ocr_api", self.tr("OCR API settings saved"))

    def _save_prompt_llm(self):
        self.config.update_section("prompt_llm", {
            "provider": self.prompt_provider_edit.text().strip(),
            "base_url": self.prompt_base_url_edit.text().strip(),
            "model": self.prompt_model_edit.text().strip(),
            "temperature": self.prompt_temp_spin.value(),
            "max_tokens": self.prompt_max_tokens_spin.value(),
        })
        self.config.set_secret("prompt_llm", self.prompt_api_key_edit.text().strip())
        self._notify_saved("prompt_llm", self.tr("Prompt LLM settings saved"))

    def _save_extract_llm(self):
        self.config.update_section("extract_llm", {
            "provider": self.extract_provider_combo.currentData(),
            "base_url": self.extract_base_url_edit.text().strip(),
            "model": self.extract_model_edit.text().strip(),
            "temperature": self.extract_temp_spin.value(),
            "max_tokens": self.extract_max_tokens_spin.value(),
        })
        self.config.set_secret("extract_llm", self.extract_api_key_edit.text().strip())
        self._notify_saved("extract_llm", self.tr("Extraction LLM settings saved"))

    def _notify_saved(self, section: str, message: str):
        from ..core import secrets
        if not secrets.LAST_BACKEND_AVAILABLE:
            message += self.tr("\n（注意：系统密钥库不可用，密钥以明文保存在配置文件中）")
        QMessageBox.information(self, self.tr("Settings"), message)
        self.settings_updated.emit(section)

    def _test_ocr_api(self):
        url = self.ocr_url_edit.text().strip()
        token = self.ocr_token_edit.text().strip()
        if not url or not token:
            QMessageBox.warning(self, self.tr("Settings"), self.tr("请先填写 OCR 接口地址和 Token"))
            return
        try:
            client = AsyncOCRClient(
                url,
                token,
                model=self.ocr_model_edit.text().strip() or DEFAULT_OCR_MODEL,
                preset=self.ocr_preset_combo.currentData() or DEFAULT_OCR_PRESET,
            )
            tiny_png = bytes.fromhex(
                "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000a49444154789c6360000002000154a20d0b0000000049454e44ae426082"
            )
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp.write(tiny_png)
                temp_path = Path(tmp.name)
            try:
                job_id = client.submit_file(temp_path)
            finally:
                temp_path.unlink(missing_ok=True)
            QMessageBox.information(self, self.tr("Settings"), self.tr("OCR 任务提交成功，jobId: %s") % job_id)
        except Exception as exc:
            QMessageBox.critical(self, self.tr("Settings"), self.tr("调用失败：%s") % exc)

    def _set_combo_data(self, combo: QComboBox, value: str):
        index = combo.findData(value)
        combo.setCurrentIndex(index if index >= 0 else 0)
