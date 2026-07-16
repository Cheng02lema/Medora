import subprocess
import sys
import time
from pathlib import Path
from typing import Dict

from PyQt5.QtCore import QObject

from .. import PROJECT_ROOT


class AppLauncher(QObject):
    """以子进程方式打开独立的传统 PyQt5 工具（保持其原始界面）。"""

    MODULES: Dict[str, str] = {
        "medical": "mee/modules/medical_extractor/Medical_Excel_Agent_Pro.py",
        "markdown": "mee/modules/markdown_converter/merge_and_convert_gui.py",
        "ocr_batch": "mee/modules/ocr_batch/ocr_batch_gui.py",
        "image_slicer": "mee/modules/image_slicer/image_slicer_qt5.py",
        "file_extractor": "mee/modules/file_extractor.py",
    }

    # 启动后探测这么久，若进程已退出则视为启动失败
    _PROBE_SECONDS = 1.2

    def __init__(self, parent=None):
        super().__init__(parent)
        self._processes: Dict[str, subprocess.Popen] = {}

    def open(self, key: str):
        """启动指定子程序。启动失败或立即崩溃时抛带友好提示的 RuntimeError。"""
        if key not in self.MODULES:
            raise KeyError(self.tr("未知的模块：%s") % key)

        # 已有实例仍在运行则直接前置提示（避免无意义多开）
        existing = self._processes.get(key)
        if existing and existing.poll() is None:
            raise RuntimeError(self.tr("该工具已在运行中，请检查是否有已打开的窗口。"))

        script_path = PROJECT_ROOT / self.MODULES[key]
        if not script_path.exists():
            raise FileNotFoundError(self.tr("脚本不存在：%s") % script_path)

        try:
            proc = subprocess.Popen(
                [sys.executable, str(script_path)],
                cwd=str(script_path.parent),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except OSError as exc:
            raise RuntimeError(self.tr("启动 %s 失败：%s") % (script_path.name, exc)) from exc

        # 短暂探测：如果进程很快退出（如缺依赖 ImportError），读取 stderr 反馈
        time.sleep(self._PROBE_SECONDS)
        if proc.poll() is not None:
            stderr = b""
            try:
                _, stderr = proc.communicate(timeout=1)
            except Exception:
                pass
            tail = stderr.decode("utf-8", errors="replace").strip().splitlines()[-6:]
            detail = "\n".join(tail) if tail else self.tr("（无错误输出）")
            raise RuntimeError(
                self.tr("%s 启动后立即退出，可能缺少依赖或脚本报错：\n%s")
                % (script_path.name, detail)
            )

        self._processes[key] = proc

    # 兼容旧调用点
    def open_medical(self):
        self.open("medical")

    def open_markdown(self):
        self.open("markdown")

    def open_ocr_batch(self):
        self.open("ocr_batch")

    def open_image_slicer(self):
        self.open("image_slicer")

    def open_file_extractor(self):
        self.open("file_extractor")
