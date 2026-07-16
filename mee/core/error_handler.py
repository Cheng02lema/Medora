import logging
import sys
import threading
import traceback
from pathlib import Path

from PyQt5.QtWidgets import QApplication, QMessageBox

from .. import PROJECT_ROOT

logger = logging.getLogger(__name__)


def _configure_logging() -> Path:
    """配置根 logger：文件 + 控制台，INFO 级别。返回日志文件路径。"""
    log_dir = PROJECT_ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "app.log"

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    fmt = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    # 避免重复添加 handler（basicConfig 可能已被其它模块调用过）
    have_file = any(
        isinstance(h, logging.FileHandler) and getattr(h, "_mee_handler", False)
        for h in root.handlers
    )
    if not have_file:
        file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
        file_handler.setFormatter(fmt)
        file_handler._mee_handler = True  # type: ignore[attr-defined]
        root.addHandler(file_handler)

    have_stream = any(
        isinstance(h, logging.StreamHandler) and getattr(h, "_mee_handler", False)
        for h in root.handlers
    )
    if not have_stream:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(fmt)
        stream_handler._mee_handler = True  # type: ignore[attr-defined]
        root.addHandler(stream_handler)

    return log_file


def install_global_exception_handler(app: QApplication):
    log_file = _configure_logging()

    def _show_dialog(trace: str):
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowTitle("应用出现异常")
        msg.setText(
            "程序遇到一个未预期的问题，但已被拦截，不会导致数据丢失。\n\n"
            "你可以：\n"
            "  • 重试刚才的操作\n"
            "  • 若反复出现，请把下方“详细信息”连同日志文件反馈给维护者\n"
            f"\n日志文件：{log_file}"
        )
        msg.setDetailedText(trace)
        msg.exec_()

    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        trace = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        logger.error("未捕获的异常:\n%s", trace)
        try:
            _show_dialog(trace)
        except Exception:
            # GUI 弹窗本身失败时不要再抛
            pass

    sys.excepthook = handle_exception

    # 捕获子线程（QThread.run 之外的原生线程）未处理异常 —— Python 3.8+
    if hasattr(threading, "excepthook"):
        def thread_hook(args):
            if issubclass(args.exc_type, KeyboardInterrupt):
                return
            trace = "".join(
                traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)
            )
            logger.error("子线程未捕获的异常 (%s):\n%s", args.thread.name, trace)

        threading.excepthook = thread_hook
