from __future__ import annotations

from pathlib import Path

import xml.etree.ElementTree as ET

from typing import Optional

from PyQt5.QtCore import QObject, QLocale, QTranslator, pyqtSignal
from PyQt5.QtWidgets import QApplication

from .. import PROJECT_ROOT


class TsTranslator(QTranslator):
    def __init__(self, ts_path: Path):
        super().__init__()
        self.translations = {}
        self._load(ts_path)

    def _load(self, path: Path):
        try:
            tree = ET.parse(str(path))
            root = tree.getroot()
        except ET.ParseError:
            return
        for context in root.findall("context"):
            name = context.findtext("name", default="")
            for message in context.findall("message"):
                source = message.findtext("source", "")
                translation = message.findtext("translation", "")
                if not source:
                    continue
                self.translations[(name, source)] = translation or source

    def translate(self, context, source_text, disambiguation=None, n=-1):
        key = (context, source_text)
        return self.translations.get(key, source_text)


class TranslatorManager(QObject):
    languageChanged = pyqtSignal(str)

    def __init__(self, app: QApplication, language: str = "en"):
        super().__init__()
        self.app = app
        self.current_language = language
        self.translator: Optional[QTranslator] = None
        self.i18n_dir = PROJECT_ROOT / "mee" / "i18n"
        self.set_language(language)

    def _load_translator(self, language: str) -> bool:
        qm_path = self.i18n_dir / f"app_{language}.qm"
        ts_path = self.i18n_dir / f"app_{language}.ts"
        if self.translator:
            self.app.removeTranslator(self.translator)
            self.translator = None
        if qm_path.exists():
            translator = QTranslator()
            if translator.load(str(qm_path)):
                self.app.installTranslator(translator)
                self.translator = translator
                return True
        if ts_path.exists():
            translator = TsTranslator(ts_path)
            self.app.installTranslator(translator)
            self.translator = translator
            return True
        return False

    def set_language(self, language: str):
        if not language:
            language = QLocale.system().name()
        self.current_language = language
        self._load_translator(language)
        self.languageChanged.emit(language)
