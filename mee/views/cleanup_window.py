from PyQt5.QtCore import QObject, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QFileDialog,
    QHBoxLayout,
    QTextEdit,
    QCheckBox,
    QSizePolicy,
)

from ..modules.cleanup import delete_matching_files


class _CleanupWorker(QThread):
    done = pyqtSignal(int, list, bool)
    failed = pyqtSignal(str)

    def __init__(self, folder: str, pattern: str, dry_run: bool):
        super().__init__()
        self.folder = folder
        self.pattern = pattern
        self.dry_run = dry_run

    def run(self):
        try:
            count, matches = delete_matching_files(self.folder, self.pattern, dry_run=self.dry_run)
            self.done.emit(count, matches, self.dry_run)
        except Exception as exc:
            self.failed.emit(str(exc))


class CleanupWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("匹配后缀删除工具"))
        self.resize(480, 360)
        self.worker = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        title = QLabel(self.tr("匹配后缀删除工具"))
        title.setObjectName("Title")
        subtitle = QLabel(self.tr("根据通配符模式批量删除指定目录下的文件，支持 Dry run 预览。"))
        subtitle.setObjectName("SubTitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        path_layout = QHBoxLayout()
        self.folder_edit = QLineEdit()
        self.folder_edit.setMinimumWidth(360)
        self.folder_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        folder_btn = QPushButton(self.tr("选择目录"))
        folder_btn.clicked.connect(self._choose_dir)
        path_layout.addWidget(self.folder_edit)
        path_layout.addWidget(folder_btn)
        layout.addLayout(path_layout)

        self.pattern_edit = QLineEdit("*右表格_0.md")
        self.pattern_edit.setMinimumWidth(360)
        self.pattern_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(self.pattern_edit)

        self.dry_run_checkbox = QCheckBox(self.tr("Dry run（仅统计，不删除）"))
        self.dry_run_checkbox.setChecked(True)
        layout.addWidget(self.dry_run_checkbox)

        self.run_btn = QPushButton(self.tr("执行清理"))
        self.run_btn.clicked.connect(self._run_cleanup)
        layout.addWidget(self.run_btn)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view, 1)

    def _choose_dir(self):
        path = QFileDialog.getExistingDirectory(self, self.tr("选择目录"))
        if path:
            self.folder_edit.setText(path)

    def _run_cleanup(self):
        folder = self.folder_edit.text().strip()
        if not folder:
            self.log_view.append(self.tr("请先选择目录"))
            return
        pattern = self.pattern_edit.text().strip() or "*右表格_0.md"
        dry_run = self.dry_run_checkbox.isChecked()

        self.run_btn.setEnabled(False)
        self.log_view.append(self.tr("正在处理…"))
        self.worker = _CleanupWorker(folder, pattern, dry_run)
        self.worker.done.connect(self._on_done)
        self.worker.failed.connect(self._on_failed)
        self.worker.finished.connect(lambda: self.run_btn.setEnabled(True))
        self.worker.start()

    def _on_done(self, count: int, matches: list, dry_run: bool):
        if dry_run:
            self.log_view.append(self.tr("Dry run：命中 %d 个文件") % count)
            preview = "\n".join(matches[:10])
            if preview:
                self.log_view.append(preview)
            if len(matches) > 10:
                self.log_view.append(self.tr("… 其余 %d 个未显示") % (len(matches) - 10))
        else:
            self.log_view.append(self.tr("已删除 %d 个文件") % count)

    def _on_failed(self, message: str):
        self.log_view.append(self.tr("清理失败：%s") % message)
