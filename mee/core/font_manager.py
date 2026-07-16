from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt5.QtCore import QFile, QIODevice
from PyQt5.QtGui import QFont, QFontDatabase
from PyQt5.QtWidgets import QApplication

from .. import PROJECT_ROOT


class FontManager:
    """Load bundled fonts and apply a consistent typography scale."""

    def __init__(self, app: QApplication, scale: float = 1.0):
        self.app = app
        self.scale = scale or 1.0
        self.font_dir = PROJECT_ROOT / "mee" / "resources" / "fonts"
        self.body_family = self._load_font(":/fonts/DejaVuSans.ttf", self.font_dir / "DejaVuSans.ttf") or "DejaVu Sans"
        self.mono_family = self._load_font(":/fonts/DejaVuSansMono.ttf", self.font_dir / "DejaVuSansMono.ttf") or "DejaVu Sans Mono"
        self._apply_global_font()

    def _load_font(self, resource_path: str, fallback_path: Path) -> Optional[str]:
        for path in (resource_path, str(fallback_path)):
            if path.startswith(":/"):
                file = QFile(path)
                if not file.exists() or not file.open(QIODevice.ReadOnly):
                    continue
                data = file.readAll()
                file.close()
                font_id = QFontDatabase.addApplicationFontFromData(data)
            else:
                local = Path(path)
                if not local.exists():
                    continue
                font_id = QFontDatabase.addApplicationFont(str(local))
            if font_id != -1:
                families = QFontDatabase.applicationFontFamilies(font_id)
                if families:
                    return families[0]
        return None

    def _apply_global_font(self):
        font = QFont(self.body_family)
        font.setPointSizeF(font.pointSizeF() * self.scale)
        self.app.setFont(font)

    def body_font(self, size: int = 0) -> QFont:
        font = QFont(self.body_family)
        if size:
            font.setPointSize(size)
        return font

    def mono_font(self, size: int = 0) -> QFont:
        font = QFont(self.mono_family)
        if size:
            font.setPointSize(size)
        return font
