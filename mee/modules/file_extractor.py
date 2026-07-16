import sys
import os
import shutil
from pathlib import Path
from fnmatch import fnmatch
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QLabel, QLineEdit,
                             QFileDialog, QTextEdit, QCheckBox, QGroupBox,
                             QProgressBar, QMessageBox)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont


class FileExtractorThread(QThread):
    """文件提取线程"""
    progress = pyqtSignal(int, int)  # 当前进度, 总数
    log = pyqtSignal(str)  # 日志信息
    finished = pyqtSignal(int)  # 完成信号，传递提取的文件数

    def __init__(self, source_dir, target_dir, extensions, pattern, keep_structure):
        super().__init__()
        self.source_dir = source_dir
        self.target_dir = target_dir
        self.extensions = extensions
        self.pattern = pattern
        self.keep_structure = keep_structure
        self.is_running = True

    def run(self):
        """执行文件提取"""
        try:
            # 查找所有匹配的文件
            matched_files = []
            source_path = Path(self.source_dir)

            self.log.emit(f"开始扫描文件夹: {self.source_dir}")

            # 递归查找所有文件
            for file_path in source_path.rglob("*"):
                if not self.is_running:
                    self.log.emit("操作已取消")
                    return

                if file_path.is_file():
                    # 检查后缀
                    if self.extensions:
                        ext_match = any(file_path.suffix.lower() == ext.lower()
                                      for ext in self.extensions)
                    else:
                        ext_match = True

                    # 检查通配符模式
                    if self.pattern:
                        pattern_match = fnmatch(file_path.name, self.pattern)
                    else:
                        pattern_match = True

                    if ext_match and pattern_match:
                        matched_files.append(file_path)

            self.log.emit(f"找到 {len(matched_files)} 个匹配的文件")

            # 复制文件
            target_path = Path(self.target_dir)
            target_path.mkdir(parents=True, exist_ok=True)

            for idx, file_path in enumerate(matched_files):
                if not self.is_running:
                    self.log.emit("操作已取消")
                    return

                try:
                    if self.keep_structure:
                        # 保持目录结构
                        rel_path = file_path.relative_to(source_path)
                        dest_file = target_path / rel_path
                        dest_file.parent.mkdir(parents=True, exist_ok=True)
                    else:
                        # 平铺到目标文件夹
                        dest_file = target_path / file_path.name

                        # 如果文件名重复，添加编号
                        counter = 1
                        original_dest = dest_file
                        while dest_file.exists():
                            dest_file = original_dest.parent / f"{original_dest.stem}_{counter}{original_dest.suffix}"
                            counter += 1

                    shutil.copy2(file_path, dest_file)
                    self.log.emit(f"[{idx+1}/{len(matched_files)}] 复制: {file_path.name} -> {dest_file}")
                    self.progress.emit(idx + 1, len(matched_files))

                except Exception as e:
                    self.log.emit(f"错误: 复制 {file_path.name} 失败 - {str(e)}")

            self.finished.emit(len(matched_files))

        except Exception as e:
            self.log.emit(f"发生错误: {str(e)}")
            self.finished.emit(0)

    def stop(self):
        """停止线程"""
        self.is_running = False


class FileExtractorApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.extractor_thread = None
        self.init_ui()

    def init_ui(self):
        """初始化UI"""
        self.setWindowTitle("文件提取工具")
        self.setGeometry(100, 100, 800, 600)

        # 主窗口部件
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout()
        main_widget.setLayout(layout)

        # 标题
        title = QLabel("文件提取工具")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # 源文件夹选择
        source_group = QGroupBox("源文件夹")
        source_layout = QHBoxLayout()
        self.source_path_edit = QLineEdit()
        self.source_path_edit.setPlaceholderText("选择要提取文件的源文件夹...")
        source_btn = QPushButton("浏览")
        source_btn.clicked.connect(self.select_source_folder)
        source_layout.addWidget(self.source_path_edit)
        source_layout.addWidget(source_btn)
        source_group.setLayout(source_layout)
        layout.addWidget(source_group)

        # 目标文件夹选择
        target_group = QGroupBox("目标文件夹")
        target_layout = QHBoxLayout()
        self.target_path_edit = QLineEdit()
        self.target_path_edit.setPlaceholderText("选择保存提取文件的目标文件夹...")
        target_btn = QPushButton("浏览")
        target_btn.clicked.connect(self.select_target_folder)
        target_layout.addWidget(self.target_path_edit)
        target_layout.addWidget(target_btn)
        target_group.setLayout(target_layout)
        layout.addWidget(target_group)

        # 过滤选项
        filter_group = QGroupBox("过滤选项")
        filter_layout = QVBoxLayout()

        # 文件后缀
        ext_layout = QHBoxLayout()
        ext_label = QLabel("文件后缀:")
        self.ext_edit = QLineEdit()
        self.ext_edit.setPlaceholderText("例如: .docx .pdf .txt (多个后缀用空格分隔，留空表示所有文件)")
        ext_layout.addWidget(ext_label)
        ext_layout.addWidget(self.ext_edit)
        filter_layout.addLayout(ext_layout)

        # 通配符模式
        pattern_layout = QHBoxLayout()
        pattern_label = QLabel("文件名模式:")
        self.pattern_edit = QLineEdit()
        self.pattern_edit.setPlaceholderText("例如: *报告* 或 *.docx (支持通配符，留空表示所有)")
        pattern_layout.addWidget(pattern_label)
        pattern_layout.addWidget(self.pattern_edit)
        filter_layout.addLayout(pattern_layout)

        # 保持目录结构选项
        self.keep_structure_checkbox = QCheckBox("保持原有目录结构")
        self.keep_structure_checkbox.setChecked(False)
        filter_layout.addWidget(self.keep_structure_checkbox)

        filter_group.setLayout(filter_layout)
        layout.addWidget(filter_group)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        # 日志显示区域
        log_group = QGroupBox("运行日志")
        log_layout = QVBoxLayout()
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)

        # 按钮区域
        button_layout = QHBoxLayout()
        self.start_btn = QPushButton("开始提取")
        self.start_btn.clicked.connect(self.start_extraction)
        self.start_btn.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; font-weight: bold; padding: 8px; }")

        self.stop_btn = QPushButton("停止")
        self.stop_btn.clicked.connect(self.stop_extraction)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("QPushButton { background-color: #f44336; color: white; font-weight: bold; padding: 8px; }")

        self.clear_btn = QPushButton("清除日志")
        self.clear_btn.clicked.connect(self.clear_log)

        button_layout.addWidget(self.start_btn)
        button_layout.addWidget(self.stop_btn)
        button_layout.addWidget(self.clear_btn)
        layout.addLayout(button_layout)

    def select_source_folder(self):
        """选择源文件夹"""
        folder = QFileDialog.getExistingDirectory(self, "选择源文件夹")
        if folder:
            self.source_path_edit.setText(folder)

    def select_target_folder(self):
        """选择目标文件夹"""
        folder = QFileDialog.getExistingDirectory(self, "选择目标文件夹")
        if folder:
            self.target_path_edit.setText(folder)

    def start_extraction(self):
        """开始提取"""
        source_dir = self.source_path_edit.text().strip()
        target_dir = self.target_path_edit.text().strip()

        # 验证输入
        if not source_dir:
            QMessageBox.warning(self, "警告", "请选择源文件夹！")
            return

        if not target_dir:
            QMessageBox.warning(self, "警告", "请选择目标文件夹！")
            return

        if not os.path.exists(source_dir):
            QMessageBox.warning(self, "警告", "源文件夹不存在！")
            return

        # 解析后缀
        ext_text = self.ext_edit.text().strip()
        extensions = []
        if ext_text:
            extensions = [ext.strip() if ext.strip().startswith('.') else '.' + ext.strip()
                         for ext in ext_text.split()]

        # 获取通配符模式
        pattern = self.pattern_edit.text().strip()

        # 获取是否保持目录结构
        keep_structure = self.keep_structure_checkbox.isChecked()

        # 清空日志
        self.log_text.clear()
        self.progress_bar.setValue(0)

        # 禁用开始按钮，启用停止按钮
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        # 创建并启动线程
        self.extractor_thread = FileExtractorThread(
            source_dir, target_dir, extensions, pattern, keep_structure
        )
        self.extractor_thread.progress.connect(self.update_progress)
        self.extractor_thread.log.connect(self.add_log)
        self.extractor_thread.finished.connect(self.extraction_finished)
        self.extractor_thread.start()

    def stop_extraction(self):
        """停止提取"""
        if self.extractor_thread:
            self.extractor_thread.stop()
            self.add_log("正在停止...")

    def update_progress(self, current, total):
        """更新进度条"""
        if total > 0:
            progress = int((current / total) * 100)
            self.progress_bar.setValue(progress)

    def add_log(self, message):
        """添加日志"""
        self.log_text.append(message)
        # 自动滚动到底部
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )

    def clear_log(self):
        """清除日志"""
        self.log_text.clear()
        self.progress_bar.setValue(0)

    def extraction_finished(self, count):
        """提取完成"""
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setValue(100)

        if count > 0:
            self.add_log(f"\n完成！成功提取 {count} 个文件")
            QMessageBox.information(self, "完成", f"成功提取 {count} 个文件！")
        else:
            self.add_log("\n未找到匹配的文件或操作已取消")


def main():
    app = QApplication(sys.argv)
    window = FileExtractorApp()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
