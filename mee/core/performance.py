from __future__ import annotations

import os
import resource
import time
from dataclasses import dataclass

from PyQt5.QtCore import QObject, QTimer, pyqtSignal


@dataclass
class PerformanceSnapshot:
    memory_mb: float
    cpu_percent: float
    load_avg: float


class PerformanceMonitor(QObject):
    metricsUpdated = pyqtSignal(PerformanceSnapshot)

    def __init__(self, parent=None, interval_ms: int = 2000):
        super().__init__(parent)
        self.interval_ms = interval_ms
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._collect)
        self._last_cpu_time = time.process_time()
        self._last_timestamp = time.time()

    def start(self):
        if not self.timer.isActive():
            self._last_cpu_time = time.process_time()
            self._last_timestamp = time.time()
            self.timer.start(self.interval_ms)

    def stop(self):
        self.timer.stop()

    def _collect(self):
        usage = resource.getrusage(resource.RUSAGE_SELF)
        memory_mb = usage.ru_maxrss / 1024.0 if os.name == "posix" else usage.ru_maxrss
        now = time.time()
        cpu_time = time.process_time()
        delta_cpu = cpu_time - self._last_cpu_time
        delta_time = now - self._last_timestamp
        cpu_percent = 0.0
        if delta_time > 0:
            cpu_percent = min(100.0, (delta_cpu / delta_time) * 100.0)
        getloadavg = getattr(os, "getloadavg", None)
        load_avg = getloadavg()[0] if callable(getloadavg) else 0.0
        snapshot = PerformanceSnapshot(memory_mb=round(memory_mb, 1), cpu_percent=round(cpu_percent, 1), load_avg=round(load_avg, 2))
        self._last_cpu_time = cpu_time
        self._last_timestamp = now
        self.metricsUpdated.emit(snapshot)
