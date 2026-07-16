from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from PyQt5.QtCore import QRunnable, QThreadPool

logger = logging.getLogger(__name__)


class Worker(QRunnable):
    def __init__(self, fn: Callable, *args, on_error: Optional[Callable[[Exception], None]] = None, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.on_error = on_error

    def run(self):
        try:
            self.fn(*self.args, **self.kwargs)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.exception("Background task failed: %s", exc)
            if self.on_error:
                self.on_error(exc)


thread_pool = QThreadPool.globalInstance()


def submit(fn: Callable, *args: Any, on_error: Optional[Callable[[Exception], None]] = None, **kwargs: Any):
    worker = Worker(fn, *args, on_error=on_error, **kwargs)
    thread_pool.start(worker)
