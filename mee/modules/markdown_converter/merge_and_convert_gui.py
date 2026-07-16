#!/usr/bin/env python3
"""
合并文件夹下的Markdown文档并转换为Word文档（PyQt5可视化界面版）
"""
import os
import re
import sys
import html
from pathlib import Path
from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from bs4 import BeautifulSoup
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QLabel, QTextEdit,
                             QFileDialog, QProgressBar, QMessageBox)
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtGui import QFont, QTextCursor



# 纯逻辑已抽离到 converter.py（供主流水线与本 GUI 共用）
try:
    from converter import (  # type: ignore
        merge_markdown_files, clean_html_tags, convert_latex_symbols,
        fix_ocr_errors, parse_html_table, add_table_to_doc, convert_md_to_docx,
    )
except ImportError:  # pragma: no cover
    from .converter import (
        merge_markdown_files, clean_html_tags, convert_latex_symbols,
        fix_ocr_errors, parse_html_table, add_table_to_doc, convert_md_to_docx,
    )



class ConvertWorker(QThread):
    """转换工作线程"""
    progress = pyqtSignal(int)
    log_message = pyqtSignal(str)
    finished = pyqtSignal(int, int)

    def __init__(self, base_dir):
        super().__init__()
        self.base_dir = base_dir
        self.is_running = True

    def run(self):
        base_path = Path(self.base_dir)

        if not base_path.exists():
            self.log_message.emit(f"错误: 目录 {self.base_dir} 不存在")
            self.finished.emit(0, 0)
            return

        folders = [f for f in base_path.iterdir() if f.is_dir()]

        if not folders:
            self.log_message.emit(f"警告: {self.base_dir} 中没有找到子文件夹")
            self.finished.emit(0, 0)
            return

        total_folders = len(folders)
        self.log_message.emit(f"找到 {total_folders} 个文件夹，开始处理...\n")

        success_count = 0
        fail_count = 0

        for idx, folder in enumerate(folders):
            if not self.is_running:
                self.log_message.emit("\n处理已取消")
                break

            folder_name = folder.name
            self.log_message.emit(f"[{idx+1}/{total_folders}] 处理文件夹: {folder_name}")

            # 合并markdown文件
            merged_content = merge_markdown_files(str(folder))

            if merged_content is None:
                self.log_message.emit(f"  ✗ 跳过: 没有找到markdown文件")
                fail_count += 1
                self.progress.emit(int((idx + 1) / total_folders * 100))
                continue

            # 保存合并后的markdown文件
            merged_md_path = folder / f"{folder_name}_merged.md"
            with open(merged_md_path, 'w', encoding='utf-8') as f:
                f.write(merged_content)
            self.log_message.emit(f"  ✓ 已保存合并的MD文件")

            # 转换为word文档
            output_docx_path = folder / f"{folder_name}.docx"

            if convert_md_to_docx(merged_content, str(output_docx_path)):
                self.log_message.emit(f"  ✓ 已生成Word文档: {output_docx_path.name}\n")
                success_count += 1
            else:
                self.log_message.emit(f"  ✗ 转换失败\n")
                fail_count += 1

            self.progress.emit(int((idx + 1) / total_folders * 100))

        self.log_message.emit("=" * 60)
        self.log_message.emit(f"处理完成！成功: {success_count} 个，失败: {fail_count} 个")
        self.log_message.emit("=" * 60)
        self.finished.emit(success_count, fail_count)

    def stop(self):
        self.is_running = False


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.worker = None
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle('Markdown转Word工具（支持HTML表格）')
        self.setGeometry(100, 100, 800, 600)

        # 主窗口部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 主布局
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)

        # 标题
        title_label = QLabel('Markdown转Word文档转换工具')
        title_font = QFont('宋体', 16, QFont.Bold)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)

        # 文件夹选择区域
        folder_layout = QHBoxLayout()
        self.folder_label = QLabel('未选择文件夹')
        self.folder_label.setStyleSheet('padding: 5px; border: 1px solid #ccc; background-color: #f5f5f5;')
        folder_layout.addWidget(self.folder_label)

        self.select_btn = QPushButton('选择文件夹')
        self.select_btn.setFont(QFont('宋体', 10))
        self.select_btn.clicked.connect(self.select_folder)
        folder_layout.addWidget(self.select_btn)

        main_layout.addLayout(folder_layout)

        # 日志显示区域
        log_label = QLabel('处理日志:')
        log_label.setFont(QFont('宋体', 10))
        main_layout.addWidget(log_label)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont('Courier New', 9))
        main_layout.addWidget(self.log_text)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        main_layout.addWidget(self.progress_bar)

        # 按钮区域
        button_layout = QHBoxLayout()

        self.start_btn = QPushButton('开始转换')
        self.start_btn.setFont(QFont('宋体', 10, QFont.Bold))
        self.start_btn.setEnabled(False)
        self.start_btn.setStyleSheet('QPushButton { background-color: #4CAF50; color: white; padding: 8px; }')
        self.start_btn.clicked.connect(self.start_conversion)
        button_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton('停止')
        self.stop_btn.setFont(QFont('宋体', 10))
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet('QPushButton { background-color: #f44336; color: white; padding: 8px; }')
        self.stop_btn.clicked.connect(self.stop_conversion)
        button_layout.addWidget(self.stop_btn)

        self.clear_btn = QPushButton('清空日志')
        self.clear_btn.setFont(QFont('宋体', 10))
        self.clear_btn.setStyleSheet('QPushButton { padding: 8px; }')
        self.clear_btn.clicked.connect(self.clear_log)
        button_layout.addWidget(self.clear_btn)

        main_layout.addLayout(button_layout)

        # 状态栏
        self.statusBar().showMessage('就绪')
        self.statusBar().setFont(QFont('宋体', 9))

        self.selected_folder = None

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, '选择包含Markdown文件的文件夹')
        if folder:
            self.selected_folder = folder
            self.folder_label.setText(folder)
            self.start_btn.setEnabled(True)
            self.log_message(f"已选择文件夹: {folder}\n")

    def start_conversion(self):
        if not self.selected_folder:
            QMessageBox.warning(self, '警告', '请先选择文件夹！')
            return

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.select_btn.setEnabled(False)
        self.progress_bar.setValue(0)

        self.worker = ConvertWorker(self.selected_folder)
        self.worker.progress.connect(self.update_progress)
        self.worker.log_message.connect(self.log_message)
        self.worker.finished.connect(self.conversion_finished)
        self.worker.start()

        self.statusBar().showMessage('正在转换...')

    def stop_conversion(self):
        if self.worker:
            self.worker.stop()
            self.stop_btn.setEnabled(False)
            self.statusBar().showMessage('正在停止...')

    def update_progress(self, value):
        self.progress_bar.setValue(value)

    def log_message(self, message):
        self.log_text.append(message)
        # 自动滚动到底部
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_text.setTextCursor(cursor)

    def clear_log(self):
        self.log_text.clear()

    def conversion_finished(self, success_count, fail_count):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.select_btn.setEnabled(True)
        self.progress_bar.setValue(100)

        if success_count + fail_count > 0:
            self.statusBar().showMessage(f'转换完成！成功: {success_count} 个，失败: {fail_count} 个')
            QMessageBox.information(self, '完成',
                                   f'转换完成！\n成功: {success_count} 个\n失败: {fail_count} 个')
        else:
            self.statusBar().showMessage('没有文件被处理')


def main():
    app = QApplication(sys.argv)

    # 检查依赖
    try:
        from docx import Document
        from bs4 import BeautifulSoup
    except ImportError as e:
        QMessageBox.critical(None, '错误',
                           f'缺少必要的库: {e}\n\n请安装:\npip install python-docx beautifulsoup4 PyQt5')
        sys.exit(1)

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
