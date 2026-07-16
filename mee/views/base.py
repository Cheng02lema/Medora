from pathlib import Path

from PyQt5.QtWidgets import QWidget, qApp

from ..config.manager import ConfigManager


class BaseView(QWidget):
    """所有界面的基类"""

    def __init__(self, config: ConfigManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.setAccessibleDescription(self.__class__.__name__)
        self.font_manager = qApp.property("font_manager")
        self.translator_manager = qApp.property("translator_manager")
        if self.translator_manager:
            self.translator_manager.languageChanged.connect(lambda _: self.retranslate())

    def retranslate(self):
        """子类可覆盖，支持动态语言切换"""
        pass
