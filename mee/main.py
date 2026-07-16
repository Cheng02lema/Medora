import sys
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

import mee.resources.resources_rc  # noqa: F401

if __package__ is None or __package__ == "":
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from mee.config.manager import ConfigManager
    from mee.views.main_window import MainWindow
    from mee import PROJECT_ROOT as _PR
    from mee.core.font_manager import FontManager
    from mee.core.theme_manager import ThemeManager
    from mee.core.translator import TranslatorManager
    from mee.core.error_handler import install_global_exception_handler
else:
    from .config.manager import ConfigManager
    from .views.main_window import MainWindow
    from . import PROJECT_ROOT
    from .core.font_manager import FontManager
    from .core.theme_manager import ThemeManager
    from .core.translator import TranslatorManager
    from .core.error_handler import install_global_exception_handler


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    app = QApplication(sys.argv)
    install_global_exception_handler(app)

    config = ConfigManager()
    config.sync_from_cloud()
    theme_manager = ThemeManager(app, config.get("ui", "theme", "dark"))
    translator_manager = TranslatorManager(app, config.get("ui", "language", "en"))
    font_manager = FontManager(app, float(config.get("ui", "font_scale", 1.0)))

    app.setOrganizationName("MedFlow")
    app.setApplicationName("MedFlow Studio")
    app.setProperty("theme_manager", theme_manager)
    app.setProperty("translator_manager", translator_manager)
    app.setProperty("font_manager", font_manager)
    app.setProperty("config_manager", config)

    window = MainWindow(config)
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
