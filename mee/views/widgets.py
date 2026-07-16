from typing import Optional

from PyQt5.QtCore import QAbstractAnimation, QEasingCurve, QPropertyAnimation
from PyQt5.QtWidgets import QGraphicsOpacityEffect, QStackedWidget


class AnimatedStackedWidget(QStackedWidget):
    """Stacked widget with a subtle fade animation when switching views."""

    def __init__(self, parent=None, duration: int = 220):
        super().__init__(parent)
        self._duration = duration
        self._current_animation: Optional[QPropertyAnimation] = None

    def setCurrentIndex(self, index: int):
        if index == self.currentIndex():
            return
        next_widget = self.widget(index)
        if next_widget is None:
            return
        effect = QGraphicsOpacityEffect(next_widget)
        next_widget.setGraphicsEffect(effect)
        effect.setOpacity(0.0)
        super().setCurrentIndex(index)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(self._duration)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.InOutQuad)

        def cleanup():
            next_widget.setGraphicsEffect(None)

        animation.finished.connect(cleanup)
        animation.start(QAbstractAnimation.DeleteWhenStopped)
        self._current_animation = animation
