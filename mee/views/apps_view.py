from typing import Callable, Dict, List, Tuple

from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QGridLayout,
    QFrame,
    QPushButton,
    QScrollArea,
    QMessageBox,
)

from ..config.manager import ConfigManager
from ..controllers.app_launcher import AppLauncher
from .base import BaseView
from .cleanup_window import CleanupWindow
from .image_mask_window import ImageMaskerWindow
from .payment_ocr_window import PaymentOCRWindow


class AppCard(QFrame):
    def __init__(self, title: str, description: str, handler: Callable[[], None]):
        super().__init__()
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        self.header = QLabel(title)
        self.header.setObjectName("CardTitle")
        self.desc = QLabel(description)
        self.desc.setObjectName("StatusSmall")
        self.desc.setWordWrap(True)
        self.btn = QPushButton()
        self.btn.clicked.connect(handler)
        layout.addWidget(self.header)
        layout.addWidget(self.desc)
        layout.addStretch()
        layout.addWidget(self.btn)


class AppsView(BaseView):
    """集中管理可以单独打开的每个功能。"""

    def __init__(self, config: ConfigManager, launcher: AppLauncher, parent=None):
        super().__init__(config, parent)
        self.launcher = launcher
        self.config = config
        self.child_windows: Dict[str, QWidget] = {}
        self.cards: List[AppCard] = []
        self._build_ui()

    def _card_specs(self) -> List[Tuple[str, str, Callable[[], None]]]:
        return [
            (self.tr("基于大模型病历提取"), self.tr("启动主 Agent，基于提取 LLM 设置解析病历。"),
             lambda: self._launch("medical")),
            (self.tr("图片去噪增强（可视化遮罩）"), self.tr("使用鼠标圈选遮罩区域并批量应用到图片。"),
             self._open_masker),
            (self.tr("批量 OCR 识别"), self.tr("使用可配置 API 对图片/PDF 进行批量 OCR。"),
             lambda: self._launch("ocr_batch")),
            (self.tr("缴费情况补救 OCR"), self.tr("匹配 -缴费情况.jpg 后缀单独补救识别。"),
             self._open_payment_ocr),
            (self.tr("Markdown 转 Word"), self.tr("批量合并 Markdown 并导出 Word。"),
             lambda: self._launch("markdown")),
            (self.tr("图片切片工具"), self.tr("可视化框选并导出多区域切片，可保存到流水线配置。"),
             lambda: self._launch("image_slicer")),
            (self.tr("匹配后缀删除工具"), self.tr("根据通配符批量删除无用 Markdown。"),
             self._open_cleanup),
            (self.tr("文件提取工具"), self.tr("按后缀/模式提取文件，可保留结构。"),
             lambda: self._launch("file_extractor")),
        ]

    def _build_ui(self):
        outer_layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer_layout.addWidget(scroll)
        container = QWidget()
        scroll.setWidget(container)
        layout = QVBoxLayout(container)

        self.title = QLabel()
        self.title.setObjectName("Title")
        self.subtitle = QLabel()
        self.subtitle.setObjectName("SubTitle")
        layout.addWidget(self.title)
        layout.addWidget(self.subtitle)

        grid = QGridLayout()
        grid.setSpacing(18)
        for idx, (name, desc, handler) in enumerate(self._card_specs()):
            card = AppCard(name, desc, handler)
            self.cards.append(card)
            grid.addWidget(card, idx // 2, idx % 2)
        layout.addLayout(grid)
        layout.addStretch()
        self.retranslate()

    def retranslate(self):
        self.title.setText(self.tr("功能模块中心"))
        self.subtitle.setText(self.tr("可单独打开每个子程序，适合调试某个环节或人工干预。"))
        specs = self._card_specs()
        for card, (name, desc, _) in zip(self.cards, specs):
            card.header.setText(name)
            card.desc.setText(desc)
            card.btn.setText(self.tr("打开"))

    def _launch(self, key: str):
        """启动外部子程序，失败时给出清晰提示而非崩溃。"""
        try:
            self.launcher.open(key)
        except Exception as exc:
            QMessageBox.critical(self, self.tr("无法打开工具"), str(exc))

    def _open_child(self, key: str, factory: Callable[[], QWidget]):
        """打开内嵌子窗口；若已存在则前置，否则新建并在关闭后从缓存移除。"""
        window = self.child_windows.get(key)
        if window is None:
            try:
                window = factory()
            except Exception as exc:
                QMessageBox.critical(self, self.tr("无法打开窗口"), str(exc))
                return
            self.child_windows[key] = window
            window.destroyed.connect(lambda *_: self.child_windows.pop(key, None))
        window.show()
        window.raise_()
        window.activateWindow()

    def _open_masker(self):
        self._open_child("masker", lambda: ImageMaskerWindow())

    def _open_payment_ocr(self):
        self._open_child("payment", lambda: PaymentOCRWindow(self.config))

    def _open_cleanup(self):
        self._open_child("cleanup", CleanupWindow)
