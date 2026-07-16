from typing import Dict, List

from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QAction,
    QLabel,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QTabBar,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
    QSplitter,
    qApp,
)

from ..config.manager import ConfigManager
from ..core.performance import PerformanceMonitor
from ..controllers.app_launcher import AppLauncher
from ..controllers.pipeline_controller import PIPELINE_STEPS, PipelineConfig, PipelineController
from ..controllers.prompt_controller import PromptController
from .apps_view import AppsView
from .pipeline_view import PipelineView
from .prompt_view import PromptView
from .settings_view import SettingsView
from .widgets import AnimatedStackedWidget


class MainWindow(QMainWindow):
    def __init__(self, config: ConfigManager):
        super().__init__()
        self.config = config
        self.pipeline_controller = PipelineController()
        self.prompt_controller = PromptController()
        self.app_launcher = AppLauncher(self)
        self.theme_manager = qApp.property("theme_manager")
        self.translator_manager = qApp.property("translator_manager")

        self.setWindowTitle(self.tr("MedFlow Studio"))
        self.setWindowIcon(QIcon(":/icons/logo.svg"))
        self.setMinimumSize(1180, 780)
        self.resize(1380, 880)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setCentralWidget(central)

        self.nav_list = QListWidget()
        self.nav_list.setObjectName("NavList")
        self.nav_list.setAccessibleName("navigationList")
        self.nav_list.setMinimumWidth(200)
        self.nav_list.setMaximumWidth(280)
        self._register_static_strings()
        self.nav_config = [
            {"key": "pipeline", "label_key": "Auto Pipeline", "icon": QIcon(":/icons/nav_pipeline.svg")},
            {"key": "prompt", "label_key": "Prompt Studio", "icon": QIcon(":/icons/nav_prompt.svg")},
            {"key": "modules", "label_key": "Modules", "icon": QIcon(":/icons/nav_modules.svg")},
            {"key": "settings", "label_key": "Settings", "icon": QIcon(":/icons/nav_settings.svg")},
        ]
        for nav in self.nav_config:
            item = QListWidgetItem(nav["icon"], "")
            item.setData(Qt.UserRole, nav["key"])
            self.nav_list.addItem(item)
        self._update_nav_labels(initial=True)
        self.nav_list.currentRowChanged.connect(self._switch_view)
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        self.tab_bar = QTabBar()
        self.tab_bar.setMovable(False)
        self.tab_bar.setDocumentMode(True)
        self.tab_bar.setDrawBase(False)
        self.tab_bar.setExpanding(False)
        self.tab_bar.currentChanged.connect(self._switch_view_from_tab)
        container_layout.addWidget(self.tab_bar)

        self.stack = AnimatedStackedWidget()
        container_layout.addWidget(self.stack, 1)

        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.addWidget(self.nav_list)
        self.main_splitter.addWidget(container)
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setCollapsible(0, False)
        layout.addWidget(self.main_splitter)

        self.pipeline_view = PipelineView(config)
        self.prompt_view = PromptView(config)
        self.apps_view = AppsView(config, self.app_launcher)
        self.settings_view = SettingsView(config)
        self.settings_view.settings_updated.connect(self._on_settings_updated)

        for idx, view in enumerate([self.pipeline_view, self.prompt_view, self.apps_view, self.settings_view]):
            self.stack.addWidget(view)
            self.tab_bar.addTab(self.nav_config[idx]["icon"], self.tr(self.nav_config[idx]["label_key"]))
        self.nav_list.setCurrentRow(0)

        self._build_toolbar()
        self._build_statusbar()
        self._last_metrics = None
        self.performance_monitor = PerformanceMonitor(self)
        self.metrics_label = QLabel()
        self.metrics_label.setObjectName("StatusSmall")
        self.statusBar().addPermanentWidget(self.metrics_label)
        self.performance_monitor.metricsUpdated.connect(self._update_metrics)
        self.performance_monitor.start()

        self.pipeline_view.start_pipeline.connect(self._start_pipeline)
        self.pipeline_view.stop_pipeline.connect(self.pipeline_controller.stop)
        self.prompt_view.start_generation.connect(self._start_prompt)
        if self.translator_manager:
            self.translator_manager.languageChanged.connect(lambda _: self._retranslate())

    def _build_toolbar(self):
        self.toolbar = QToolBar(self.tr("Global Actions"))
        self.toolbar.setIconSize(QSize(20, 20))
        self.addToolBar(Qt.TopToolBarArea, self.toolbar)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(self.tr("Global search..."))
        self.search_edit.setMinimumWidth(280)
        self.search_edit.setAccessibleName("globalSearch")
        search_action = QWidgetAction(self)
        search_action.setDefaultWidget(self.search_edit)
        self.toolbar.addAction(search_action)

        self.theme_action = QAction(QIcon(":/icons/theme_dark.svg"), self.tr("Toggle Theme"), self)
        self.theme_action.triggered.connect(self._toggle_theme)
        self.theme_action.setToolTip(self.tr("Switch between dark/light/high contrast themes"))
        self.toolbar.addAction(self.theme_action)

        language_menu = QMenu(self)
        english_action = language_menu.addAction("English")
        english_action.triggered.connect(lambda: self._change_language("en"))
        chinese_action = language_menu.addAction("简体中文")
        chinese_action.triggered.connect(lambda: self._change_language("zh_CN"))
        self.language_button = QToolButton()
        self.language_button.setIcon(QIcon(":/icons/language.svg"))
        self.language_button.setText(self.tr("Language"))
        self.language_button.setPopupMode(QToolButton.InstantPopup)
        self.language_button.setMenu(language_menu)
        lang_action = QWidgetAction(self)
        lang_action.setDefaultWidget(self.language_button)
        self.toolbar.addAction(lang_action)

    def _register_static_strings(self):
        for text in ("Auto Pipeline", "Prompt Studio", "Modules", "Settings"):
            self.tr(text)

    def _build_statusbar(self):
        status = self.statusBar()
        status.showMessage(self.tr("Ready"))

    def _update_metrics(self, snapshot):
        self._last_metrics = snapshot
        text = self.tr("CPU {cpu}% · RAM {ram} MB · Load {load}").format(
            cpu=f"{snapshot.cpu_percent:.1f}",
            ram=f"{snapshot.memory_mb:.1f}",
            load=f"{snapshot.load_avg:.2f}",
        )
        self.metrics_label.setText(text)

    def _switch_view(self, index: int):
        self._activate_workspace(index, source="nav")

    def _switch_view_from_tab(self, index: int):
        self._activate_workspace(index, source="tab")

    def _activate_workspace(self, index: int, source: str):
        if index < 0:
            return
        self.stack.setCurrentIndex(index)
        if source != "tab":
            self.tab_bar.blockSignals(True)
            self.tab_bar.setCurrentIndex(index)
            self.tab_bar.blockSignals(False)
        if source != "nav":
            self.nav_list.blockSignals(True)
            self.nav_list.setCurrentRow(index)
            self.nav_list.blockSignals(False)
        current_text = self.tab_bar.tabText(index)
        self.statusBar().showMessage(self.tr("Current workspace: %s") % current_text)

    def _start_pipeline(self, params: Dict):
        try:
            pipeline_config = self._build_pipeline_config(params)
        except Exception as exc:
            self.pipeline_view.append_log(self.tr("配置错误：%s") % exc)
            self.pipeline_view.set_running(False)
            return
        self.pipeline_view.set_running(True)
        worker = self.pipeline_controller.run(pipeline_config)
        worker.log.connect(self.pipeline_view.append_log)
        worker.step_changed.connect(lambda key: self.pipeline_view.update_step_status(key, self.tr("Running"), "running"))
        worker.step_completed.connect(lambda key, state, msg: self.pipeline_view.update_step_status(key, msg, state))
        worker.finished.connect(lambda success, msg: self._on_pipeline_finished(success, msg))

    def _build_pipeline_config(self, params: Dict) -> PipelineConfig:
        selected_steps = params.pop("selected_steps", [step.key for step in PIPELINE_STEPS])
        extraction_template = params.pop("extraction_template", "").strip()
        extract_conf = self.config.data.get("extract_llm", {})
        extract_llm = {
            "provider": extract_conf.get("provider", ""),
            "api_key": self.config.get_secret("extract_llm"),
            "api_url": extract_conf.get("base_url", "") or "",
            "model": extract_conf.get("model", "gpt-4o-mini"),
            "temperature": extract_conf.get("temperature", 0.0),
            "max_tokens": extract_conf.get("max_tokens", 8000),
        }
        return PipelineConfig(
            scenario=params["scenario"],
            raw_input=params["raw_input"],
            preprocess_output=params["preprocess_output"],
            ocr_output=params["ocr_output"],
            api_url=params["api_url"],
            api_token=params["api_token"],
            ocr_model=params["ocr_model"],
            ocr_preset=params["ocr_preset"],
            file_extensions=params["file_extensions"],
            enable_payment_ocr=params["enable_payment_ocr"],
            payment_pattern=params["payment_pattern"],
            cleanup_target=params["cleanup_target"],
            cleanup_pattern=params["cleanup_pattern"],
            selected_steps=selected_steps,
            extraction_template=extraction_template,
            output_excel=params.get("output_excel", "").strip(),
            extract_llm=extract_llm,
        )

    def _on_pipeline_finished(self, success: bool, message: str):
        self.pipeline_view.append_log(message)
        self.pipeline_view.set_running(False)

    def _start_prompt(self, params: Dict):
        self.prompt_view.set_running(True)
        worker = self.prompt_controller.start(params)
        worker.progress.connect(self.prompt_view.append_log)
        worker.finished.connect(lambda success, msg: self._on_prompt_finished(success, msg))

    def _on_prompt_finished(self, success: bool, message: str):
        self.prompt_view.append_log(message)
        self.prompt_view.set_running(False)

    def _on_settings_updated(self, section: str):
        if section in {"pipeline", "ocr_api"}:
            self.pipeline_view.refresh_from_config(section)
        if section in {"prompt", "prompt_llm"}:
            self.prompt_view.refresh_from_config(section)

    def _update_nav_labels(self, initial: bool = False):
        for idx, nav in enumerate(self.nav_config):
            item = self.nav_list.item(idx)
            if item:
                item.setText(self.tr(nav["label_key"]))
            if not initial and hasattr(self, "tab_bar") and idx < self.tab_bar.count():
                self.tab_bar.setTabText(idx, self.tr(nav["label_key"]))

    def _toggle_theme(self):
        if self.theme_manager:
            self.theme_manager.toggle()
            self.config.update_section("ui", {"theme": self.theme_manager.current_theme})

    def _change_language(self, language: str):
        if self.translator_manager:
            self.translator_manager.set_language(language)
            self.config.update_section("ui", {"language": language})
            self._retranslate()

    def _retranslate(self):
        self.setWindowTitle(self.tr("MedFlow Studio"))
        if hasattr(self, "toolbar"):
            self.toolbar.setWindowTitle(self.tr("Global Actions"))
        self.search_edit.setPlaceholderText(self.tr("Global search..."))
        if hasattr(self, "theme_action"):
            self.theme_action.setText(self.tr("Toggle Theme"))
            self.theme_action.setToolTip(self.tr("Switch between dark/light/high contrast themes"))
        if hasattr(self, "language_button"):
            self.language_button.setText(self.tr("Language"))
        self._update_nav_labels()
        self._update_nav_labels()
        if getattr(self, "_last_metrics", None):
            self._update_metrics(self._last_metrics)
        self.toolbar.setWindowTitle(self.tr("Global Actions"))
        self.search_edit.setPlaceholderText(self.tr("Global search..."))
        self.statusBar().showMessage(self.tr("Ready"))
        if hasattr(self, "language_button"):
            self.language_button.setText(self.tr("Language"))
        self._update_nav_labels()
