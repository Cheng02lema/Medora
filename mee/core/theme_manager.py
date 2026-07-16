from __future__ import annotations

from pathlib import Path
from typing import Dict

from PyQt5.QtCore import QFile, QObject, pyqtSignal
from PyQt5.QtWidgets import QApplication

from .. import PROJECT_ROOT


PALETTES: Dict[str, Dict[str, str]] = {
    "dark": {
        "@BACKGROUND@": "#0f172a",
        "@TEXT@": "#e2e8f0",
        "@TEXT-SUBTLE@": "#94a3b8",
        "@TEXT-DISABLED@": "#475569",
        "@PRIMARY@": "#2563eb",
        "@PRIMARY-HOVER@": "#1d4ed8",
        "@PRIMARY-ACTIVE@": "#1e40af",
        "@PRIMARY-FADE@": "rgba(37,99,235,0.18)",
        "@SURFACE@": "#111826",
        "@BORDER@": "rgba(148, 163, 184, 0.25)",
        "@SCROLL-HANDLE@": "#2f3545",
        "@DISABLED@": "#475569",
        "@SUCCESS@": "#22c55e",
        "@WARNING@": "#f97316",
        "@ERROR@": "#ef4444",
        "@ACCENT@": "#14b8a6",
        "@ACCENT-FADE@": "rgba(20, 184, 166, 0.15)",
    },
    "light": {
        "@BACKGROUND@": "#f8fafc",
        "@TEXT@": "#1e293b",
        "@TEXT-SUBTLE@": "#475569",
        "@TEXT-DISABLED@": "#94a3b8",
        "@PRIMARY@": "#2563eb",
        "@PRIMARY-HOVER@": "#1d4ed8",
        "@PRIMARY-ACTIVE@": "#1e40af",
        "@PRIMARY-FADE@": "rgba(37,99,235,0.10)",
        "@SURFACE@": "#ffffff",
        "@BORDER@": "#e2e8f0",
        "@SCROLL-HANDLE@": "#cbd5f5",
        "@DISABLED@": "#e2e8f0",
        "@SUCCESS@": "#16a34a",
        "@WARNING@": "#f97316",
        "@ERROR@": "#dc2626",
        "@ACCENT@": "#0ea5e9",
        "@ACCENT-FADE@": "rgba(14,165,233,0.12)",
    },
    "high_contrast": {
        "@BACKGROUND@": "#000000",
        "@TEXT@": "#ffffff",
        "@TEXT-SUBTLE@": "#f5f5f5",
        "@TEXT-DISABLED@": "#cbd5f5",
        "@PRIMARY@": "#ffffff",
        "@PRIMARY-HOVER@": "#cbd5f5",
        "@PRIMARY-ACTIVE@": "#94a3b8",
        "@PRIMARY-FADE@": "rgba(255,255,255,0.3)",
        "@SURFACE@": "#000000",
        "@BORDER@": "#ffffff",
        "@SCROLL-HANDLE@": "#ffffff",
        "@DISABLED@": "#4b5563",
        "@SUCCESS@": "#ffffff",
        "@WARNING@": "#facc15",
        "@ERROR@": "#f87171",
        "@ACCENT@": "#ffffff",
        "@ACCENT-FADE@": "rgba(255,255,255,0.25)",
    },
}


class ThemeManager(QObject):
    themeChanged = pyqtSignal(str)

    def __init__(self, app: QApplication, initial_theme: str = "dark"):
        super().__init__()
        self.app = app
        self.current_theme = initial_theme if initial_theme in PALETTES else "dark"
        self.components_dir = PROJECT_ROOT / "mee" / "resources" / "qss" / "components"
        self.theme_dir = PROJECT_ROOT / "mee" / "resources" / "qss" / "themes"
        self._apply_theme(self.current_theme)

    def _component_files(self):
        return sorted(path.name for path in self.components_dir.glob("*.qss"))

    def _read_file(self, base_dir: Path, folder: str, filename: str) -> str:
        resource_path = f":/{folder}/{filename}"
        qfile = QFile(resource_path)
        if qfile.exists() and qfile.open(QFile.ReadOnly | QFile.Text):
            data = bytes(qfile.readAll()).decode("utf-8")
            qfile.close()
            return data
        path = base_dir / filename
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""

    def _build_stylesheet(self, theme: str) -> str:
        palette = PALETTES[theme]
        chunks = [self._read_file(self.components_dir, "qss/components", name) for name in self._component_files()]
        chunks.append(self._read_file(self.theme_dir, "qss/themes", f"{theme}.qss"))
        stylesheet = "\n".join(chunks)
        for token, value in palette.items():
            stylesheet = stylesheet.replace(token, value)
        return stylesheet

    def _apply_theme(self, theme: str):
        stylesheet = self._build_stylesheet(theme)
        self.app.setStyleSheet(stylesheet)
        self.current_theme = theme
        self.themeChanged.emit(theme)

    def toggle(self):
        order = ["dark", "light", "high_contrast"]
        idx = order.index(self.current_theme)
        new_theme = order[(idx + 1) % len(order)]
        self._apply_theme(new_theme)

    def set_theme(self, theme: str):
        if theme in PALETTES:
            self._apply_theme(theme)
