from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from PyQt5.QtCore import QPoint, QRect, Qt, QThread, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QLineEdit,
)

from .. import PROJECT_ROOT
from ..modules.image_preprocess import ImagePreprocessor


class _PreprocessWorker(QThread):
    """后台执行批量预处理，避免阻塞 UI。"""

    log = pyqtSignal(str)
    finished_ok = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, config: dict, input_dir: str, output_dir: str):
        super().__init__()
        self.config = config
        self.input_dir = input_dir
        self.output_dir = output_dir

    def run(self):
        try:
            preprocessor = ImagePreprocessor(config_data=self.config, log_callback=self.log.emit)
            preprocessor.process_folder(self.input_dir, self.output_dir, recursive=True)
            self.finished_ok.emit()
        except Exception as exc:
            self.failed.emit(str(exc))


class MaskCanvas(QLabel):
    regionCreated = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(500, 500)
        self.setStyleSheet("background-color:#0f131c; border:1px solid #333;")
        self.original_pixmap: Optional[QPixmap] = None
        self.display_pixmap: Optional[QPixmap] = None
        self.scale_factor = 1.0
        self.offset = QPoint()
        self.drawing = False
        self.start_point = QPoint()
        self.end_point = QPoint()
        self.mask_regions: List[dict] = []

    def load_image(self, path: str):
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return False
        self.original_pixmap = pixmap
        self._update_display()
        self.mask_regions.clear()
        self.update()
        return True

    def _update_display(self):
        if not self.original_pixmap:
            return
        label_size = self.size()
        pixmap_size = self.original_pixmap.size()
        scale = min(label_size.width() / pixmap_size.width(), label_size.height() / pixmap_size.height())
        scale = min(scale, 1.0)
        self.scale_factor = scale
        new_size = pixmap_size * scale
        self.display_pixmap = self.original_pixmap.scaled(new_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.offset = QPoint((label_size.width() - new_size.width()) // 2, (label_size.height() - new_size.height()) // 2)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_display()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.display_pixmap:
            if not self._point_in_image(event.pos()):
                return
            self.drawing = True
            self.start_point = event.pos()
            self.end_point = event.pos()
            self.update()

    def mouseMoveEvent(self, event):
        if self.drawing:
            self.end_point = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.drawing:
            self.drawing = False
            self.end_point = event.pos()
            if self._point_in_image(self.start_point) and self._point_in_image(self.end_point):
                rect = self._to_image_rect(QRect(self.start_point, self.end_point))
                if rect.width() > 5 and rect.height() > 5:
                    region = {"x": rect.x(), "y": rect.y(), "width": rect.width(), "height": rect.height(), "color": "black"}
                    self.mask_regions.append(region)
                    self.regionCreated.emit(region)
            self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        if self.display_pixmap:
            painter.drawPixmap(self.offset, self.display_pixmap)
        pen = QPen(QColor("#3a7afe"))
        pen.setWidth(2)
        painter.setPen(pen)
        for region in self.mask_regions:
            rect = QRect(
                self.offset.x() + int(region["x"] * self.scale_factor),
                self.offset.y() + int(region["y"] * self.scale_factor),
                int(region["width"] * self.scale_factor),
                int(region["height"] * self.scale_factor),
            )
            painter.drawRect(rect)
        if self.drawing and self.display_pixmap:
            draw_rect = QRect(self.start_point, self.end_point)
            painter.setPen(QPen(QColor("#ffcf44"), 2, Qt.DashLine))
            painter.drawRect(draw_rect)

    def _point_in_image(self, point: QPoint) -> bool:
        if not self.display_pixmap:
            return False
        rect = QRect(self.offset, self.display_pixmap.size())
        return rect.contains(point)

    def _to_image_rect(self, rect: QRect) -> QRect:
        if not self.display_pixmap:
            return QRect()
        top_left = QPoint(
            max(0, rect.left() - self.offset.x()),
            max(0, rect.top() - self.offset.y()),
        )
        bottom_right = QPoint(
            min(self.display_pixmap.width(), rect.right() - self.offset.x()),
            min(self.display_pixmap.height(), rect.bottom() - self.offset.y()),
        )
        img_rect = QRect(top_left, bottom_right).normalized()
        return QRect(
            int(img_rect.x() / self.scale_factor),
            int(img_rect.y() / self.scale_factor),
            int(img_rect.width() / self.scale_factor),
            int(img_rect.height() / self.scale_factor),
        )


class ImageMaskerWindow(QWidget):
    """图片去噪遮罩可视化工具"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("图片去噪增强（可视化遮罩）")
        self.resize(1100, 700)
        self.config_path = PROJECT_ROOT / "mee/resources/preprocess_config.json"
        self.mask_regions: List[dict] = []
        self.worker = None
        self._build_ui()
        self._load_existing_masks()

    def _build_ui(self):
        layout = QHBoxLayout(self)

        self.canvas = MaskCanvas()
        layout.addWidget(self.canvas, 2)

        right_panel = QVBoxLayout()

        open_btn = QPushButton("选择样例图片")
        open_btn.clicked.connect(self._open_image)
        right_panel.addWidget(open_btn)

        self.mask_list = QListWidget()
        right_panel.addWidget(self.mask_list, 1)

        btn_row = QHBoxLayout()
        del_btn = QPushButton("删除选中遮罩")
        del_btn.clicked.connect(self._delete_selected_mask)
        clear_btn = QPushButton("清空遮罩")
        clear_btn.clicked.connect(self._clear_masks)
        btn_row.addWidget(del_btn)
        btn_row.addWidget(clear_btn)
        right_panel.addLayout(btn_row)

        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("输入文件夹…")
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("输出文件夹…")
        for edit in (self.input_edit, self.output_edit):
            edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        select_layout = QHBoxLayout()
        input_btn = QPushButton("选择输入")
        input_btn.clicked.connect(lambda: self._choose_dir(self.input_edit))
        output_btn = QPushButton("选择输出")
        output_btn.clicked.connect(lambda: self._choose_dir(self.output_edit))
        select_layout.addWidget(self.input_edit)
        select_layout.addWidget(input_btn)
        select_layout.addWidget(self.output_edit)
        select_layout.addWidget(output_btn)
        right_panel.addLayout(select_layout)

        run_btn = QPushButton("应用到文件夹")
        run_btn.clicked.connect(self._run_preprocess)
        save_btn = QPushButton("保存遮罩配置")
        save_btn.clicked.connect(self._save_masks)
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(run_btn)
        btn_layout.addWidget(save_btn)
        right_panel.addLayout(btn_layout)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        right_panel.addWidget(self.log_view, 1)

        layout.addLayout(right_panel, 1)

        self.canvas.regionCreated.connect(self._on_region_created)

    def _open_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择图片", filter="Images (*.png *.jpg *.jpeg *.bmp)")
        if path and self.canvas.load_image(path):
            self.append_log(f"已加载 {path}")

    def _on_region_created(self, region: dict):
        self.mask_regions.append(region)
        self._refresh_mask_list()

    def _refresh_mask_list(self):
        self.mask_list.clear()
        for idx, region in enumerate(self.mask_regions, start=1):
            item = QListWidgetItem(f"{idx}. x={region['x']} y={region['y']} w={region['width']} h={region['height']}")
            self.mask_list.addItem(item)

    def _delete_selected_mask(self):
        row = self.mask_list.currentRow()
        if row >= 0:
            self.mask_regions.pop(row)
            if row < len(self.canvas.mask_regions):
                self.canvas.mask_regions.pop(row)
            self._refresh_mask_list()
            self.canvas.update()

    def _clear_masks(self):
        self.mask_regions.clear()
        self.canvas.mask_regions.clear()
        self._refresh_mask_list()
        self.canvas.update()

    def _choose_dir(self, target: QLineEdit):
        path = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if path:
            target.setText(path)

    def _run_preprocess(self):
        input_dir = self.input_edit.text().strip()
        output_dir = self.output_edit.text().strip()
        if not input_dir or not output_dir:
            self.append_log("请先选择输入和输出文件夹")
            return
        if self.worker and self.worker.isRunning():
            self.append_log("已有预处理任务在运行中")
            return
        config = {
            "mask_regions": self.mask_regions,
            "enhance_params": {
                "contrast": 2.0,
                "sharpness": 2.0,
                "brightness": 1.2,
                "denoise": True,
                "binarize": False,
            },
        }
        self.append_log("开始批量预处理…")
        self.worker = _PreprocessWorker(config, input_dir, output_dir)
        self.worker.log.connect(self.append_log)
        self.worker.finished_ok.connect(lambda: self.append_log("✓ 批量预处理完成"))
        self.worker.failed.connect(lambda msg: self.append_log(f"✗ 预处理失败：{msg}"))
        self.worker.start()

    def _save_masks(self):
        config = {
            "mask_regions": self.mask_regions,
            "enhance_params": {
                "contrast": 2.8,
                "sharpness": 3.5,
                "brightness": 1.8,
                "denoise": False,
                "binarize": True,
                "binarize_threshold": 140,
            },
        }
        self.config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        self.append_log(f"遮罩配置已保存到 {self.config_path}")

    def _load_existing_masks(self):
        if not self.config_path.exists():
            return
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
            self.mask_regions = data.get("mask_regions", [])
            self.canvas.mask_regions = list(self.mask_regions)
            self._refresh_mask_list()
        except (json.JSONDecodeError, OSError) as exc:
            self.append_log(f"遮罩配置读取失败（将从空白开始）：{exc}")

    def append_log(self, message: str):
        self.log_view.append(message)
