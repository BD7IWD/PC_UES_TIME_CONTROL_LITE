# -*- coding: utf-8 -*-
"""提醒气泡：置顶、不抢焦点、自动消失。

作者：野怼怼；https://www.bd7iwd.com
许可：MIT
"""
from __future__ import annotations

from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (QApplication, QFrame, QLabel, QVBoxLayout, QWidget)


class Toast(QWidget):
    """一条提醒气泡。"""

    closed = pyqtSignal()

    def __init__(self, text: str, seconds: int = 15, level: str = 'info'):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_DeleteOnClose, True)

        warn = (level == 'warn')
        bg = 'rgba(214, 96, 20, 240)' if warn else 'rgba(18, 26, 42, 238)'
        border = 'rgba(255, 176, 90, 255)' if warn else 'rgba(90, 140, 240, 160)'

        frame = QFrame(self)
        frame.setStyleSheet(
            f'QFrame {{ background: {bg}; border: 1px solid {border}; border-radius: 18px; }}'
        )

        lay = QVBoxLayout(frame)
        lay.setContentsMargins(30, 22, 30, 22)
        lay.setSpacing(8)

        icon = QLabel('⏰' if not warn else '📢', frame)
        icon.setAlignment(Qt.AlignCenter)
        f = QFont()
        f.setPointSize(26)
        icon.setFont(f)
        icon.setStyleSheet('color: #ffffff; background: transparent; border: none;')
        lay.addWidget(icon)

        self.lbl = QLabel(text, frame)
        self.lbl.setAlignment(Qt.AlignCenter)
        self.lbl.setWordWrap(True)
        self.lbl.setMaximumWidth(680)
        f2 = QFont()
        f2.setPointSize(20)
        f2.setBold(True)
        self.lbl.setFont(f2)
        self.lbl.setStyleSheet('color: #ffffff; background: transparent; border: none;')
        lay.addWidget(self.lbl)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(frame)

        self.adjustSize()
        self._place()

        self.setWindowOpacity(0.0)
        self._anim_in = QPropertyAnimation(self, b'windowOpacity', self)
        self._anim_in.setDuration(220)
        self._anim_in.setStartValue(0.0)
        self._anim_in.setEndValue(1.0)

        self._seconds = max(3, int(seconds))
        QTimer.singleShot(self._seconds * 1000, self.fade_out)

    def _place(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        self.adjustSize()
        x = geo.x() + (geo.width() - self.width()) // 2
        y = geo.y() + 70
        self.move(x, y)

    def show_toast(self) -> None:
        self.setWindowOpacity(0.0)
        self.show()
        self._anim_in.start()
        try:
            QApplication.beep()
        except Exception:
            pass

    def fade_out(self) -> None:
        self._anim_out = QPropertyAnimation(self, b'windowOpacity', self)
        self._anim_out.setDuration(320)
        self._anim_out.setStartValue(self.windowOpacity())
        self._anim_out.setEndValue(0.0)
        self._anim_out.finished.connect(self.close)
        self._anim_out.start()

    def closeEvent(self, ev):
        self.closed.emit()
        super().closeEvent(ev)


class ToastManager:
    """同一时刻只保留一条提醒，新提醒顶掉旧的。"""

    def __init__(self) -> None:
        self._cur: Toast | None = None

    def show(self, text: str, seconds: int = 15, level: str = 'info') -> None:
        if self._cur is not None:
            try:
                self._cur.close()
            except Exception:
                pass
            self._cur = None
        t = Toast(text, seconds, level)
        self._cur = t
        t.closed.connect(self._on_closed)
        t.show_toast()

    def _on_closed(self) -> None:
        self._cur = None
