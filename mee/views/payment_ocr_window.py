from typing import Optional

from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QFileDialog,
    QTextEdit,
    QHBoxLayout,
    QWidget,
    QFormLayout,
    QSizePolicy,
    QComboBox,
)

from ..config.manager import ConfigManager
from ..modules.payment_ocr import process_payment_images
from ..modules.ocr_client import DEFAULT_OCR_MODEL
from ..modules.ocr_presets import DEFAULT_OCR_PRESET, get_ocr_preset_options


class PaymentWorker(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(self, params: dict):
        super().__init__()
        self.params = params

    def run(self):
        try:
            count = process_payment_images(
                input_dir=self.params["input_dir"],
                output_dir=self.params["output_dir"],
                api_url=self.params["api_url"],
                token=self.params["token"],
                model=self.params["model"],
                preset=self.params["preset"],
                pattern=self.params["pattern"],
                log_callback=lambda msg: self.progress.emit(msg),
            )
            self.finished.emit(True, f"任务完成，共处理 {count} 个文件")
        except Exception as exc:
            self.finished.emit(False, f"任务失败: {exc}")


class PaymentOCRWindow(QWidget):
    def __init__(self, config: ConfigManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.worker: Optional[PaymentWorker] = None
        self.setWindowTitle("缴费情况补救 OCR")
        self.resize(520, 480)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        title = QLabel("缴费情况补救 OCR")
        title.setObjectName("Title")
        subtitle = QLabel("针对 -缴费情况.jpg 后缀进行单独 OCR 识别，便于补救识别失败的票据。")
        subtitle.setObjectName("SubTitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        form = QFormLayout()
        self.input_edit = QLineEdit(self.config.get("pipeline", "raw_input", ""))
        input_btn = QPushButton("选择")
        input_btn.clicked.connect(lambda: self._choose_dir(self.input_edit))
        form.addRow("输入目录", self._combine(self.input_edit, input_btn))

        self.output_edit = QLineEdit(self.config.get("pipeline", "ocr_output", ""))
        output_btn = QPushButton("选择")
        output_btn.clicked.connect(lambda: self._choose_dir(self.output_edit))
        form.addRow("输出目录", self._combine(self.output_edit, output_btn))

        ocr_conf = self.config.data.get("ocr_api", {})
        self.api_url_edit = QLineEdit(ocr_conf.get("url", ""))
        self.api_url_edit.setMinimumWidth(320)
        self.api_url_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        form.addRow("API 地址", self.api_url_edit)
        self.api_token_edit = QLineEdit(self.config.get_secret("ocr_api"))
        self.api_token_edit.setEchoMode(QLineEdit.Password)
        self.api_token_edit.setMinimumWidth(320)
        self.api_token_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        form.addRow("API Token", self.api_token_edit)

        self.model_edit = QLineEdit(ocr_conf.get("model", DEFAULT_OCR_MODEL))
        self.model_edit.setMinimumWidth(320)
        self.model_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        form.addRow("OCR 模型", self.model_edit)

        self.preset_combo = QComboBox()
        for label, value in get_ocr_preset_options():
            self.preset_combo.addItem(label, value)
        self._set_combo_data(self.preset_combo, ocr_conf.get("preset", DEFAULT_OCR_PRESET))
        form.addRow("OCR 预设", self.preset_combo)

        self.pattern_edit = QLineEdit(self.config.get("pipeline", "payment_pattern", "-缴费情况.jpg"))
        self.pattern_edit.setMinimumWidth(320)
        self.pattern_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        form.addRow("匹配后缀", self.pattern_edit)

        container = QWidget()
        container.setLayout(form)
        layout.addWidget(container)

        self.start_btn = QPushButton("开始补救 OCR")
        self.start_btn.clicked.connect(self._start)
        layout.addWidget(self.start_btn)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view, 1)

    def _combine(self, edit: QLineEdit, btn: QPushButton) -> QWidget:
        wrapper = QWidget()
        h = QHBoxLayout(wrapper)
        h.setContentsMargins(0, 0, 0, 0)
        edit.setMinimumWidth(320)
        edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        h.addWidget(edit)
        h.addWidget(btn)
        return wrapper

    def _choose_dir(self, target: QLineEdit):
        path = QFileDialog.getExistingDirectory(self, "选择目录")
        if path:
            target.setText(path)

    def _start(self):
        if self.worker:
            return
        params = {
            "input_dir": self.input_edit.text().strip(),
            "output_dir": self.output_edit.text().strip(),
            "api_url": self.api_url_edit.text().strip(),
            "token": self.api_token_edit.text().strip(),
            "model": self.model_edit.text().strip() or DEFAULT_OCR_MODEL,
            "preset": self.preset_combo.currentData() or DEFAULT_OCR_PRESET,
            "pattern": self.pattern_edit.text().strip() or "-缴费情况.jpg",
        }
        if not all(params.values()):
            self.log_view.append("请填写完整参数")
            return
        self.worker = PaymentWorker(params)
        self.worker.progress.connect(self.log_view.append)
        self.worker.finished.connect(self._on_finished)
        self.worker.start()
        self.start_btn.setEnabled(False)

    def _on_finished(self, success: bool, message: str):
        self.log_view.append(message)
        self.start_btn.setEnabled(True)
        self.worker = None

    def _set_combo_data(self, combo: QComboBox, value: str):
        index = combo.findData(value)
        combo.setCurrentIndex(index if index >= 0 else 0)
