#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图片切片工具 - PyQt5版本
支持自定义切片区域、批量处理、自定义命名
"""

import sys
import os
from pathlib import Path
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QLabel, QLineEdit,
                             QListWidget, QTextEdit, QFileDialog, QMessageBox,
                             QProgressBar, QSplitter, QGroupBox, QScrollArea)
from PyQt5.QtCore import Qt, QRect, QThread, pyqtSignal, QPoint
from PyQt5.QtGui import QPixmap, QImage, QPainter, QPen, QColor, QFont
from PIL import Image
import json

# 切片纯逻辑已抽离到 slicer.py（供主流水线与本 GUI 共用）
try:
    from slicer import apply_slices  # type: ignore
except ImportError:  # pragma: no cover
    from .slicer import apply_slices


def region_to_dict(region):
    """把 SliceRegion 转成 slicer.apply_slices 接受的 dict。"""
    return {"name": region.name, "x1": region.x1, "y1": region.y1, "x2": region.x2, "y2": region.y2}


class SliceRegion:
    """切片区域类"""
    def __init__(self, name, x1, y1, x2, y2):
        self.name = name
        self.x1 = min(x1, x2)
        self.y1 = min(y1, y2)
        self.x2 = max(x1, x2)
        self.y2 = max(y1, y2)

    def get_coords(self):
        return (self.x1, self.y1, self.x2, self.y2)

    def __repr__(self):
        return f"{self.name}: ({self.x1}, {self.y1}, {self.x2}, {self.y2})"


class ImageLabel(QLabel):
    """自定义图片标签，支持鼠标绘制"""

    # 定义信号：当绘制完成时发出 (x1, y1, x2, y2)
    regionDrawn = pyqtSignal(int, int, int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("background-color: #2b2b2b; border: 1px solid #555;")
        self.setMinimumSize(600, 400)

        self.original_pixmap = None
        self.display_pixmap = None
        self.scale_factor = 1.0

        self.drawing = False
        self.start_point = QPoint()
        self.end_point = QPoint()
        self.current_rect = QRect()

        self.slice_regions = []
        self.colors = [
            QColor(255, 0, 0),      # 红
            QColor(0, 255, 0),      # 绿
            QColor(0, 0, 255),      # 蓝
            QColor(255, 255, 0),    # 黄
            QColor(255, 0, 255),    # 品红
            QColor(0, 255, 255),    # 青
            QColor(255, 128, 0),    # 橙
        ]

    def set_image(self, image_path):
        """设置图片"""
        self.original_pixmap = QPixmap(image_path)
        if self.original_pixmap.isNull():
            return False

        self.scale_and_display()
        return True

    def scale_and_display(self):
        """缩放并显示图片"""
        if not self.original_pixmap:
            return

        # 计算缩放比例
        label_size = self.size()
        pixmap_size = self.original_pixmap.size()

        scale_w = label_size.width() / pixmap_size.width()
        scale_h = label_size.height() / pixmap_size.height()
        self.scale_factor = min(scale_w, scale_h, 1.0)

        # 缩放图片
        scaled_size = pixmap_size * self.scale_factor
        self.display_pixmap = self.original_pixmap.scaled(
            scaled_size, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )

        self.update()

    def resizeEvent(self, event):
        """窗口大小改变时重新缩放"""
        super().resizeEvent(event)
        if self.original_pixmap:
            self.scale_and_display()

    def paintEvent(self, event):
        """绘制事件"""
        super().paintEvent(event)

        if not self.display_pixmap:
            return

        painter = QPainter(self)

        # 绘制图片（居中）
        x = (self.width() - self.display_pixmap.width()) // 2
        y = (self.height() - self.display_pixmap.height()) // 2
        painter.drawPixmap(x, y, self.display_pixmap)

        # 绘制所有已保存的切片区域
        for i, region in enumerate(self.slice_regions):
            color = self.colors[i % len(self.colors)]
            pen = QPen(color, 2)
            painter.setPen(pen)

            # 转换坐标
            rx1 = int(region.x1 * self.scale_factor) + x
            ry1 = int(region.y1 * self.scale_factor) + y
            rx2 = int(region.x2 * self.scale_factor) + x
            ry2 = int(region.y2 * self.scale_factor) + y

            painter.drawRect(rx1, ry1, rx2 - rx1, ry2 - ry1)

            # 绘制标签
            painter.setFont(QFont("Arial", 10, QFont.Bold))
            painter.drawText(rx1 + 5, ry1 + 15, region.name)

        # 绘制当前正在绘制的矩形
        if self.drawing:
            pen = QPen(QColor(255, 255, 255), 2, Qt.DashLine)
            painter.setPen(pen)
            painter.drawRect(self.current_rect)

    def get_image_offset(self):
        """获取图片在标签中的偏移量"""
        if not self.display_pixmap:
            return 0, 0
        x = (self.width() - self.display_pixmap.width()) // 2
        y = (self.height() - self.display_pixmap.height()) // 2
        return x, y

    def mousePressEvent(self, event):
        """鼠标按下"""
        if event.button() == Qt.LeftButton and self.original_pixmap:
            self.drawing = True
            self.start_point = event.pos()
            self.current_rect = QRect(self.start_point, self.start_point)

    def mouseMoveEvent(self, event):
        """鼠标移动"""
        if self.drawing:
            self.end_point = event.pos()
            self.current_rect = QRect(self.start_point, self.end_point).normalized()
            self.update()

    def mouseReleaseEvent(self, event):
        """鼠标释放"""
        if event.button() == Qt.LeftButton and self.drawing:
            self.drawing = False
            self.end_point = event.pos()

            # 检查矩形大小
            if abs(self.end_point.x() - self.start_point.x()) < 5 or \
               abs(self.end_point.y() - self.start_point.y()) < 5:
                self.update()
                return

            # 转换为原始图片坐标
            offset_x, offset_y = self.get_image_offset()

            x1 = int((self.start_point.x() - offset_x) / self.scale_factor)
            y1 = int((self.start_point.y() - offset_y) / self.scale_factor)
            x2 = int((self.end_point.x() - offset_x) / self.scale_factor)
            y2 = int((self.end_point.y() - offset_y) / self.scale_factor)

            # 限制在图片范围内
            img_width = self.original_pixmap.width()
            img_height = self.original_pixmap.height()

            x1 = max(0, min(x1, img_width))
            y1 = max(0, min(y1, img_height))
            x2 = max(0, min(x2, img_width))
            y2 = max(0, min(y2, img_height))

            self.update()

            # 发出信号
            self.regionDrawn.emit(x1, y1, x2, y2)

    def add_region(self, region):
        """添加切片区域"""
        self.slice_regions.append(region)
        self.update()

    def remove_region(self, index):
        """删除切片区域"""
        if 0 <= index < len(self.slice_regions):
            self.slice_regions.pop(index)
            self.update()

    def clear_regions(self):
        """清空所有区域"""
        self.slice_regions.clear()
        self.update()


class BatchProcessThread(QThread):
    """批量处理线程"""
    progress = pyqtSignal(int)
    log = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, input_folder, output_folder, slice_regions):
        super().__init__()
        self.input_folder = input_folder
        self.output_folder = output_folder
        self.slice_regions = slice_regions

    def run(self):
        """执行批量处理（委托给 slicer.apply_slices 纯逻辑）"""
        try:
            regions = [region_to_dict(r) for r in self.slice_regions]
            success, fail = apply_slices(
                self.input_folder, self.output_folder, regions, log_callback=self.log.emit
            )
            self.progress.emit(100)
            self.log.emit(f"\n批量处理完成! 成功 {success}，失败 {fail}")
        except Exception as e:
            self.log.emit(f"批量处理错误: {str(e)}")
        self.finished.emit()


class ImageSlicerGUI(QMainWindow):
    """主窗口"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("图片切片工具 - PyQt5版")
        self.setGeometry(100, 100, 1400, 900)

        # 数据
        self.current_image_path = None
        self.input_folder = None
        self.output_folder = None
        self.processing_thread = None

        self.init_ui()

    def init_ui(self):
        """初始化UI"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)

        # 创建分割器
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)

        # === 左侧控制面板 ===
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_widget.setMaximumWidth(350)

        # 1. 图片加载区
        load_group = QGroupBox("1. 加载示例图片")
        load_layout = QVBoxLayout()

        self.load_btn = QPushButton("选择示例图片")
        self.load_btn.setMinimumHeight(35)
        self.load_btn.clicked.connect(self.load_sample_image)
        load_layout.addWidget(self.load_btn)

        self.image_info_label = QLabel("未加载图片")
        self.image_info_label.setStyleSheet("color: gray; padding: 5px;")
        load_layout.addWidget(self.image_info_label)

        load_group.setLayout(load_layout)
        left_layout.addWidget(load_group)

        # 2. 切片区域管理
        slice_group = QGroupBox("2. 定义切片区域")
        slice_layout = QVBoxLayout()

        # 切片名称输入
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("切片名称:"))
        self.slice_name_input = QLineEdit("slice1")
        name_layout.addWidget(self.slice_name_input)
        slice_layout.addLayout(name_layout)

        # 提示
        tip_label = QLabel("💡 在右侧图片上拖拽鼠标框选区域")
        tip_label.setStyleSheet("color: #4a9eff; padding: 5px; font-size: 11px;")
        tip_label.setWordWrap(True)
        slice_layout.addWidget(tip_label)

        # 切片列表
        self.slice_list = QListWidget()
        self.slice_list.setMinimumHeight(150)
        slice_layout.addWidget(self.slice_list)

        # 按钮
        self.delete_btn = QPushButton("删除选中的切片")
        self.delete_btn.clicked.connect(self.delete_selected_slice)
        slice_layout.addWidget(self.delete_btn)

        self.clear_btn = QPushButton("清空所有切片")
        self.clear_btn.clicked.connect(self.clear_all_slices)
        slice_layout.addWidget(self.clear_btn)

        slice_group.setLayout(slice_layout)
        left_layout.addWidget(slice_group)

        # 3. 批量处理区
        batch_group = QGroupBox("3. 批量处理")
        batch_layout = QVBoxLayout()

        self.input_btn = QPushButton("选择输入文件夹")
        self.input_btn.setMinimumHeight(30)
        self.input_btn.clicked.connect(self.select_input_folder)
        batch_layout.addWidget(self.input_btn)

        self.input_label = QLabel("未选择")
        self.input_label.setStyleSheet("color: gray; padding: 3px; font-size: 10px;")
        self.input_label.setWordWrap(True)
        batch_layout.addWidget(self.input_label)

        self.output_btn = QPushButton("选择输出文件夹")
        self.output_btn.setMinimumHeight(30)
        self.output_btn.clicked.connect(self.select_output_folder)
        batch_layout.addWidget(self.output_btn)

        self.output_label = QLabel("未选择")
        self.output_label.setStyleSheet("color: gray; padding: 3px; font-size: 10px;")
        self.output_label.setWordWrap(True)
        batch_layout.addWidget(self.output_label)

        self.process_btn = QPushButton("开始批量处理")
        self.process_btn.setMinimumHeight(40)
        self.process_btn.setStyleSheet("background-color: #4a9eff; color: white; font-weight: bold;")
        self.process_btn.clicked.connect(self.start_batch_process)
        batch_layout.addWidget(self.process_btn)

        # 保存切片区域到配置，供主流水线的 slice 步自动应用
        self.save_config_btn = QPushButton("保存切片区域到流水线配置")
        self.save_config_btn.setMinimumHeight(32)
        self.save_config_btn.clicked.connect(self.save_regions_to_config)
        batch_layout.addWidget(self.save_config_btn)

        self.progress_bar = QProgressBar()
        batch_layout.addWidget(self.progress_bar)

        batch_group.setLayout(batch_layout)
        left_layout.addWidget(batch_group)

        left_layout.addStretch()

        # === 右侧图片显示区 ===
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        # 图片显示
        self.image_label = ImageLabel()
        self.image_label.regionDrawn.connect(self.on_region_drawn)
        right_layout.addWidget(self.image_label, stretch=3)

        # 日志区
        log_group = QGroupBox("处理日志")
        log_layout = QVBoxLayout()

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        self.log_text.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4; font-family: Monaco, Menlo, monospace;")
        log_layout.addWidget(self.log_text)

        log_group.setLayout(log_layout)
        right_layout.addWidget(log_group, stretch=1)

        # 添加到分割器
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

    def log(self, message):
        """添加日志"""
        self.log_text.append(message)

    def load_sample_image(self):
        """加载示例图片"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择示例图片",
            "",
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.tiff *.tif);;所有文件 (*.*)"
        )

        if not file_path:
            return

        if self.image_label.set_image(file_path):
            self.current_image_path = file_path
            filename = os.path.basename(file_path)

            # 获取图片尺寸
            pixmap = self.image_label.original_pixmap
            size_text = f"{pixmap.width()}x{pixmap.height()}"

            self.image_info_label.setText(f"{filename}\n尺寸: {size_text}")
            self.image_info_label.setStyleSheet("color: black; padding: 5px;")

            self.log(f"已加载示例图片: {filename} ({size_text})")
        else:
            QMessageBox.warning(self, "错误", "无法加载图片")

    def on_region_drawn(self, x1, y1, x2, y2):
        """当绘制区域完成时的槽函数"""
        # 获取切片名称
        slice_name = self.slice_name_input.text().strip()

        if not slice_name:
            QMessageBox.warning(self, "提示", "请输入切片名称!")
            return

        # 创建切片区域
        region = SliceRegion(slice_name, x1, y1, x2, y2)

        # 添加到列表
        self.image_label.add_region(region)
        self.slice_list.addItem(str(region))

        self.log(f"已添加切片: {region}")

        # 自动增加切片名称
        self.auto_increment_slice_name()

    def auto_increment_slice_name(self):
        """自动增加切片名称数字"""
        import re
        current_name = self.slice_name_input.text()

        match = re.search(r'(\d+)$', current_name)
        if match:
            num = int(match.group(1))
            prefix = current_name[:match.start()]
            new_name = f"{prefix}{num + 1}"
            self.slice_name_input.setText(new_name)
        else:
            self.slice_name_input.setText(f"{current_name}2")

    def delete_selected_slice(self):
        """删除选中的切片"""
        current_row = self.slice_list.currentRow()

        if current_row < 0:
            QMessageBox.information(self, "提示", "请先选择要删除的切片")
            return

        self.image_label.remove_region(current_row)
        self.slice_list.takeItem(current_row)

        self.log(f"已删除切片 (索引: {current_row})")

    def clear_all_slices(self):
        """清空所有切片"""
        if self.slice_list.count() == 0:
            return

        reply = QMessageBox.question(
            self,
            "确认",
            "确定要清空所有切片吗?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.image_label.clear_regions()
            self.slice_list.clear()
            self.log("已清空所有切片")

    def select_input_folder(self):
        """选择输入文件夹"""
        folder = QFileDialog.getExistingDirectory(self, "选择输入文件夹")

        if folder:
            self.input_folder = folder
            self.input_label.setText(folder)
            self.input_label.setStyleSheet("color: black; padding: 3px; font-size: 10px;")
            self.log(f"输入文件夹: {folder}")

    def select_output_folder(self):
        """选择输出文件夹"""
        folder = QFileDialog.getExistingDirectory(self, "选择输出文件夹")

        if folder:
            self.output_folder = folder
            self.output_label.setText(folder)
            self.output_label.setStyleSheet("color: black; padding: 3px; font-size: 10px;")
            self.log(f"输出文件夹: {folder}")

    def start_batch_process(self):
        """开始批量处理"""
        # 验证
        if len(self.image_label.slice_regions) == 0:
            QMessageBox.warning(self, "提示", "请先定义至少一个切片区域!")
            return

        if not self.input_folder:
            QMessageBox.warning(self, "提示", "请选择输入文件夹!")
            return

        if not self.output_folder:
            QMessageBox.warning(self, "提示", "请选择输出文件夹!")
            return

        # 禁用按钮
        self.process_btn.setEnabled(False)
        self.progress_bar.setValue(0)

        # 创建处理线程
        self.processing_thread = BatchProcessThread(
            self.input_folder,
            self.output_folder,
            self.image_label.slice_regions
        )

        self.processing_thread.progress.connect(self.update_progress)
        self.processing_thread.log.connect(self.log)
        self.processing_thread.finished.connect(self.on_process_finished)

        self.processing_thread.start()

    def update_progress(self, value):
        """更新进度条"""
        self.progress_bar.setValue(value)

    def on_process_finished(self):
        """处理完成"""
        self.process_btn.setEnabled(True)
        QMessageBox.information(self, "完成", "批量处理完成!")

    def save_regions_to_config(self):
        """把当前切片区域保存到 resources/slice_config.json，供主流水线自动应用。"""
        regions = [region_to_dict(r) for r in self.image_label.slice_regions]
        if not regions:
            QMessageBox.warning(self, "提示", "请先定义至少一个切片区域!")
            return
        # 定位项目根下的 resources 目录（本文件在 mee/modules/image_slicer/ 下）
        config_path = Path(__file__).resolve().parents[2] / "resources" / "slice_config.json"
        try:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(
                json.dumps({"regions": regions}, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            QMessageBox.information(self, "已保存", f"切片区域已保存到\n{config_path}\n流水线的“图片切片”步骤会自动应用。")
        except OSError as exc:
            QMessageBox.critical(self, "保存失败", f"无法写入配置文件：{exc}")


def main():
    app = QApplication(sys.argv)

    # 设置样式
    app.setStyle('Fusion')

    window = ImageSlicerGUI()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
