#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量OCR处理 - Qt5可视化界面
支持批量处理多个文件夹中的图片和 PDF，使用PaddleOCR API进行OCR识别
"""

import sys
import os
import json
from pathlib import Path
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QLabel, QProgressBar,
                             QTextEdit, QFileDialog, QLineEdit, QGroupBox,
                             QMessageBox, QCheckBox, QComboBox)
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtGui import QFont
import requests

try:
    from ..ocr_client import AsyncOCRClient, DEFAULT_OCR_JOB_URL, DEFAULT_OCR_MODEL, save_layout_results
    from ..ocr_presets import DEFAULT_OCR_PRESET, get_ocr_preset_options
except ImportError:  # pragma: no cover - direct script execution
    from pathlib import Path as _Path
    import sys as _sys

    _sys.path.append(str(_Path(__file__).resolve().parents[2]))
    from modules.ocr_client import AsyncOCRClient, DEFAULT_OCR_JOB_URL, DEFAULT_OCR_MODEL, save_layout_results
    from modules.ocr_presets import DEFAULT_OCR_PRESET, get_ocr_preset_options


class OCRWorker(QThread):
    """OCR处理工作线程"""
    progress = pyqtSignal(int, int, str)  # 当前进度, 总数, 消息
    log = pyqtSignal(str)  # 日志信息
    finished = pyqtSignal(bool, str)  # 是否成功, 消息

    def __init__(self, root_dir, api_url, token, output_dir, file_extensions, model, preset):
        super().__init__()
        self.root_dir = root_dir
        self.api_url = api_url
        self.token = token
        self.output_dir = output_dir
        self.file_extensions = file_extensions
        self.is_running = True
        self.model = model or DEFAULT_OCR_MODEL
        self.preset = preset or DEFAULT_OCR_PRESET

    def run(self):
        """执行OCR批处理"""
        try:
            # 收集所有待 OCR 文件
            self.log.emit(f"正在扫描目录: {self.root_dir}")
            image_files = self.collect_files()

            if not image_files:
                self.finished.emit(False, "未找到任何可识别文件")
                return

            total = len(image_files)
            self.log.emit(f"找到 {total} 个文件")

            # 创建输出目录
            os.makedirs(self.output_dir, exist_ok=True)
            client = AsyncOCRClient(
                job_url=self.api_url,
                token=self.token,
                model=self.model,
                preset=self.preset,
                log_callback=lambda msg: self.log.emit(msg),
            )

            # 批量处理
            success_count = 0
            failed_count = 0

            for idx, img_path in enumerate(image_files):
                if not self.is_running:
                    self.log.emit("处理已取消")
                    break

                # 更新进度
                self.progress.emit(idx + 1, total, f"正在处理: {img_path.name}")

                # 处理单个文件
                try:
                    results = client.process_file(img_path)
                    if results:
                        # 保存结果
                        self.save_result(img_path, results)
                        success_count += 1
                        self.log.emit(f"✓ 成功: {img_path.name}")
                    else:
                        failed_count += 1
                        self.log.emit(f"✗ 失败: {img_path.name}")
                except Exception as e:
                    failed_count += 1
                    self.log.emit(f"✗ 错误 {img_path.name}: {str(e)}")

            # 完成
            msg = f"处理完成！成功: {success_count}, 失败: {failed_count}"
            self.finished.emit(True, msg)

        except Exception as e:
            self.finished.emit(False, f"发生错误: {str(e)}")

    def collect_files(self):
        """收集所有待 OCR 的文件"""
        image_files = []
        root_path = Path(self.root_dir)

        # 遍历所有子目录
        for file_path in root_path.rglob('*'):
            if file_path.is_file() and file_path.suffix.lower() in self.file_extensions:
                image_files.append(file_path)

        return sorted(image_files)

    def save_result(self, img_path, results):
        """保存OCR结果"""
        # 构建输出路径，保持原有的目录结构
        rel_path = img_path.relative_to(self.root_dir)
        output_base = Path(self.output_dir) / rel_path.parent / rel_path.stem
        output_base.parent.mkdir(parents=True, exist_ok=True)
        save_layout_results(results, output_base)

    def stop(self):
        """停止处理"""
        self.is_running = False


class OCRBatchGUI(QMainWindow):
    """批量OCR处理主窗口"""

    def __init__(self):
        super().__init__()
        self.worker = None
        self.config_file = "config.json"
        self.load_config()
        self.init_ui()

    def init_ui(self):
        """初始化界面"""
        self.setWindowTitle("批量OCR处理工具")
        self.setGeometry(100, 100, 900, 700)

        # 主窗口部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # 标题
        title = QLabel("批量OCR图片识别系统")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title)

        # API配置组
        api_group = QGroupBox("API配置")
        api_layout = QVBoxLayout()

        # API URL
        url_layout = QHBoxLayout()
        url_layout.addWidget(QLabel("API地址:"))
        self.api_url_input = QLineEdit()
        self.api_url_input.setText(self.config.get("api_url", ""))
        url_layout.addWidget(self.api_url_input)
        api_layout.addLayout(url_layout)

        model_layout = QHBoxLayout()
        model_layout.addWidget(QLabel("模型:"))
        self.model_input = QLineEdit()
        self.model_input.setText(self.config.get("model", DEFAULT_OCR_MODEL))
        model_layout.addWidget(self.model_input)
        api_layout.addLayout(model_layout)

        # Token
        token_layout = QHBoxLayout()
        token_layout.addWidget(QLabel("Token:"))
        self.token_input = QLineEdit()
        self.token_input.setText(self.config.get("token", ""))
        self.token_input.setEchoMode(QLineEdit.Password)
        token_layout.addWidget(self.token_input)

        self.show_token_checkbox = QCheckBox("显示")
        self.show_token_checkbox.stateChanged.connect(self.toggle_token_visibility)
        token_layout.addWidget(self.show_token_checkbox)
        api_layout.addLayout(token_layout)

        preset_layout = QHBoxLayout()
        preset_layout.addWidget(QLabel("预设:"))
        self.preset_input = QComboBox()
        for label, value in get_ocr_preset_options():
            self.preset_input.addItem(label, value)
        self._set_combo_data(self.preset_input, self.config.get("preset", DEFAULT_OCR_PRESET))
        preset_layout.addWidget(self.preset_input)
        api_layout.addLayout(preset_layout)

        api_group.setLayout(api_layout)
        main_layout.addWidget(api_group)

        # 目录选择组
        dir_group = QGroupBox("目录配置")
        dir_layout = QVBoxLayout()

        # 输入目录
        input_layout = QHBoxLayout()
        input_layout.addWidget(QLabel("输入目录:"))
        self.input_dir_input = QLineEdit()
        self.input_dir_input.setText(self.config.get("input_dir", ""))
        input_layout.addWidget(self.input_dir_input)
        self.browse_input_btn = QPushButton("浏览...")
        self.browse_input_btn.clicked.connect(self.browse_input_dir)
        input_layout.addWidget(self.browse_input_btn)
        dir_layout.addLayout(input_layout)

        # 输出目录
        output_layout = QHBoxLayout()
        output_layout.addWidget(QLabel("输出目录:"))
        self.output_dir_input = QLineEdit()
        self.output_dir_input.setText(self.config.get("output_dir", "output"))
        output_layout.addWidget(self.output_dir_input)
        self.browse_output_btn = QPushButton("浏览...")
        self.browse_output_btn.clicked.connect(self.browse_output_dir)
        output_layout.addWidget(self.browse_output_btn)
        dir_layout.addLayout(output_layout)

        dir_group.setLayout(dir_layout)
        main_layout.addWidget(dir_group)

        # 进度条
        progress_group = QGroupBox("处理进度")
        progress_layout = QVBoxLayout()

        self.status_label = QLabel("就绪")
        progress_layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)

        progress_group.setLayout(progress_layout)
        main_layout.addWidget(progress_group)

        # 日志窗口
        log_group = QGroupBox("处理日志")
        log_layout = QVBoxLayout()

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Courier", 9))
        log_layout.addWidget(self.log_text)

        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group)

        # 控制按钮
        btn_layout = QHBoxLayout()

        self.start_btn = QPushButton("开始处理")
        self.start_btn.clicked.connect(self.start_processing)
        self.start_btn.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; font-size: 14px; padding: 8px; }")
        btn_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("停止")
        self.stop_btn.clicked.connect(self.stop_processing)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("QPushButton { background-color: #f44336; color: white; font-size: 14px; padding: 8px; }")
        btn_layout.addWidget(self.stop_btn)

        self.clear_log_btn = QPushButton("清空日志")
        self.clear_log_btn.clicked.connect(self.clear_log)
        btn_layout.addWidget(self.clear_log_btn)

        self.save_config_btn = QPushButton("保存配置")
        self.save_config_btn.clicked.connect(self.save_config)
        btn_layout.addWidget(self.save_config_btn)

        main_layout.addLayout(btn_layout)

    def load_config(self):
        """加载配置"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
            except:
                self.config = {}
        else:
            self.config = {
                "api_url": DEFAULT_OCR_JOB_URL,
                "model": DEFAULT_OCR_MODEL,
                "preset": DEFAULT_OCR_PRESET,
                "token": "",
                "input_dir": "./切片",
                "output_dir": "./output"
            }

    def save_config(self):
        """保存配置"""
        self.config = {
            "api_url": self.api_url_input.text(),
            "model": self.model_input.text(),
            "preset": self.preset_input.currentData(),
            "token": self.token_input.text(),
            "input_dir": self.input_dir_input.text(),
            "output_dir": self.output_dir_input.text()
        }

        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            self.append_log("配置已保存")
            QMessageBox.information(self, "成功", "配置已保存")
        except Exception as e:
            QMessageBox.warning(self, "错误", f"保存配置失败: {str(e)}")

    def toggle_token_visibility(self, state):
        """切换Token显示/隐藏"""
        if state == Qt.Checked:
            self.token_input.setEchoMode(QLineEdit.Normal)
        else:
            self.token_input.setEchoMode(QLineEdit.Password)

    def _set_combo_data(self, combo, value):
        index = combo.findData(value)
        combo.setCurrentIndex(index if index >= 0 else 0)

    def browse_input_dir(self):
        """浏览输入目录"""
        directory = QFileDialog.getExistingDirectory(self, "选择输入目录")
        if directory:
            self.input_dir_input.setText(directory)

    def browse_output_dir(self):
        """浏览输出目录"""
        directory = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if directory:
            self.output_dir_input.setText(directory)

    def start_processing(self):
        """开始处理"""
        # 验证输入
        api_url = self.api_url_input.text().strip()
        model = self.model_input.text().strip()
        preset = self.preset_input.currentData() or DEFAULT_OCR_PRESET
        token = self.token_input.text().strip()
        input_dir = self.input_dir_input.text().strip()
        output_dir = self.output_dir_input.text().strip()

        if not all([api_url, model, preset, token, input_dir, output_dir]):
            QMessageBox.warning(self, "警告", "请填写所有必要信息")
            return

        if not os.path.exists(input_dir):
            QMessageBox.warning(self, "警告", f"输入目录不存在: {input_dir}")
            return

        # 禁用按钮
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        # 清空日志和进度
        self.progress_bar.setValue(0)
        self.append_log("=" * 50)
        self.append_log("开始批量处理...")

        # 创建工作线程
        file_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.pdf'}
        self.worker = OCRWorker(input_dir, api_url, token, output_dir, file_extensions, model, preset)
        self.worker.progress.connect(self.update_progress)
        self.worker.log.connect(self.append_log)
        self.worker.finished.connect(self.processing_finished)
        self.worker.start()

    def stop_processing(self):
        """停止处理"""
        if self.worker:
            self.worker.stop()
            self.append_log("正在停止处理...")

    def update_progress(self, current, total, message):
        """更新进度"""
        progress = int((current / total) * 100)
        self.progress_bar.setValue(progress)
        self.status_label.setText(f"进度: {current}/{total} - {message}")

    def append_log(self, message):
        """添加日志"""
        self.log_text.append(message)
        # 自动滚动到底部
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def clear_log(self):
        """清空日志"""
        self.log_text.clear()

    def processing_finished(self, success, message):
        """处理完成"""
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.append_log("=" * 50)
        self.append_log(message)

        if success:
            QMessageBox.information(self, "完成", message)
        else:
            QMessageBox.warning(self, "失败", message)

        self.status_label.setText("就绪")


def main():
    app = QApplication(sys.argv)
    window = OCRBatchGUI()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
