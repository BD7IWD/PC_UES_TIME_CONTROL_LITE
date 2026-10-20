# -*- coding: utf-8 -*-
"""锁定画面：
  1) 假 Windows 蓝屏（默认，最像"电脑坏了"）
  2) 假"电脑已损坏"错误弹窗

画面本身不允许任何操作（真蓝屏也不会响应鼠标键盘）。
家长用手机打开管控页面点「解除锁定」，或在蓝屏上双击 `:(` 走本地密码后门。

作者：野怼怼；https://www.bd7iwd.com
许可：MIT
"""
from __future__ import annotations

import random
import time

from PyQt5.QtCore import QEventLoop, QRect, Qt, QTimer, pyqtSignal, QObject
from PyQt5.QtGui import QColor, QFont, QFontDatabase, QPainter, QPen
from PyQt5.QtWidgets import (QApplication, QDialog, QFrame, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QVBoxLayout, QWidget)

from core import config, store

BSOD_BG = '#0078D7'      # Win10 蓝屏底色
BSOD_BG_11 = '#101418'   # Win11 黑屏底色

#: 隐藏后门：在锁定画面上快速连点鼠标 N 次，弹出解锁密码框
CLICK_TARGET = 10
CLICK_WINDOW = 6.0       # 这 N 次点击需在多少秒内完成


class _PwdDialog(QDialog):
    """解锁密码框：固定尺寸 + 手动居中 + 置顶。

    两个坑：
      1. 蓝屏是「总在最前」的全屏窗口，对话框必须也置顶，否则被压在下面看不见；
      2. QDialog.exec_() 会按系统/父窗口规则重新摆放窗口，move() 会被覆盖，
         所以这里改用 show() + QEventLoop，位置完全由我们自己定。
    """

    W, H = 470, 232

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('系统恢复')
        self.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint)
        self.setWindowModality(Qt.ApplicationModal)
        self.setFixedSize(self.W, self.H)
        self.setStyleSheet('''
            QDialog { background: #1b2430; }
            QLabel { color: #e8eef7; background: transparent; }
            QLabel#title { font-size: 17px; font-weight: 700; }
            QLabel#tip { color: #93a4bb; font-size: 12.5px; }
            QLineEdit { background: #0f1620; color: #ffffff; border: 1px solid #3a4a60;
                        border-radius: 8px; padding: 10px 12px; font-size: 16px;
                        letter-spacing: 4px; }
            QLineEdit:focus { border-color: #4a90e2; }
            QPushButton { background: #2d6cdf; color: #ffffff; border: none;
                          border-radius: 8px; padding: 9px 24px; font-size: 14px; }
            QPushButton#cancel { background: #2a3547; color: #cfdae8; }
        ''')

        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 22, 26, 20)
        lay.setSpacing(11)

        t = QLabel('系统恢复')
        t.setObjectName('title')
        lay.addWidget(t)

        tip = QLabel('输入恢复密钥以继续：')
        tip.setObjectName('tip')
        lay.addWidget(tip)

        self.edit = QLineEdit()
        self.edit.setEchoMode(QLineEdit.Password)
        self.edit.setPlaceholderText('恢复密钥')
        self.edit.returnPressed.connect(self.accept)
        lay.addWidget(self.edit)

        row = QHBoxLayout()
        row.addStretch(1)
        b_cancel = QPushButton('取消')
        b_cancel.setObjectName('cancel')
        b_cancel.clicked.connect(self.reject)
        b_ok = QPushButton('确定')
        b_ok.setDefault(True)
        b_ok.clicked.connect(self.accept)
        row.addWidget(b_cancel)
        row.addWidget(b_ok)
        lay.addLayout(row)

    def place_centered(self) -> None:
        scr = self.screen() or QApplication.primaryScreen()
        if scr is None:
            return
        c = scr.geometry().center()
        fg = self.frameGeometry()      # 含标题栏，才能真正视觉居中
        fg.moveCenter(c)
        self.move(fg.topLeft())

    def textValue(self) -> str:
        return self.edit.text()


def prompt_unlock(parent=None) -> bool:
    """弹出解锁密码框并校验。返回 True 表示已解锁成功（并已写入数据库）。"""
    dlg = _PwdDialog(parent)
    dlg.place_centered()

    loop = QEventLoop()
    dlg.finished.connect(loop.quit)
    dlg.show()
    dlg.place_centered()      # DPI 下 show 后尺寸才最终确定，再校一次
    dlg.raise_()
    dlg.activateWindow()
    dlg.edit.setFocus()
    loop.exec_()

    ok = (dlg.result() == QDialog.Accepted)
    pwd = dlg.textValue()
    try:
        dlg.hide()
        dlg.deleteLater()
    except Exception:
        pass
    if not ok or not pwd:
        return False

    s = store.get_settings()
    if s.get('unlock_hash') and store.verify_pwd(pwd, s['unlock_hash']):
        store.update_settings(locked=0, lock_reason=None)
        store.reset_used()
        store.bump_unlock()
        store.add_event('unlocked', '锁定画面后门：输入密码解锁')
        config.log('[backdoor] 密码正确，解锁')
        return True
    store.add_event('unlock_failed', '锁定画面后门：密码错误')
    config.log('[backdoor] 密码错误')
    return False


def _font(size: int, bold: bool = False, family: str = 'Segoe UI') -> QFont:
    f = QFont(family, size)
    f.setBold(bold)
    return f


class FakeQR(QWidget):
    """画一个像模像样的假二维码（真蓝屏右下角有）。"""

    def __init__(self, parent=None, size: int = 100):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._n = 25
        rnd = random.Random(0xB50D)
        self._grid = [[rnd.random() < 0.45 for _ in range(self._n)] for _ in range(self._n)]

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        s = self.width()
        n = self._n
        cell = s / n
        p.fillRect(0, 0, s, s, QColor('#ffffff'))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor('#000000'))
        for y in range(n):
            for x in range(n):
                if self._grid[y][x]:
                    p.drawRect(QRect(int(x * cell), int(y * cell),
                                     max(1, int(cell) + 1), max(1, int(cell) + 1)))
        # 三个定位角
        for (ox, oy) in ((0, 0), (n - 7, 0), (0, n - 7)):
            p.fillRect(int(ox * cell), int(oy * cell), int(cell * 7), int(cell * 7), QColor('#ffffff'))
            p.fillRect(int(ox * cell), int(oy * cell), int(cell * 7), int(cell * 7), QColor('#000000'))
            p.fillRect(int((ox + 1) * cell), int((oy + 1) * cell),
                       int(cell * 5), int(cell * 5), QColor('#ffffff'))
            p.fillRect(int((ox + 2) * cell), int((oy + 2) * cell),
                       int(cell * 3), int(cell * 3), QColor('#000000'))
        p.end()


class _ScreenOverlay(QWidget):
    """一块屏幕的全屏遮罩基类。"""

    def __init__(self, allow_close: bool = False):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Window)
        self.allow_close = allow_close
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.BlankCursor)

    def keyPressEvent(self, ev):
        ev.accept()

    def closeEvent(self, ev):
        if self.allow_close:
            ev.accept()
        else:
            ev.ignore()

    def show_over(self, screen):
        try:
            if self.windowHandle():
                self.windowHandle().setScreen(screen)
        except Exception:
            pass
        self.setGeometry(screen.geometry())
        self.show()
        self.raise_()


class BsodScreen(_ScreenOverlay):
    """假蓝屏。主屏带隐藏解锁后门，副屏纯色。"""

    unlock_requested = pyqtSignal()

    def __init__(self, primary: bool = True, code: str = 'CRITICAL_PROCESS_DIED',
                 dark: bool = False):
        super().__init__()
        self.primary = primary
        self.dark = dark
        self.code = code or 'CRITICAL_PROCESS_DIED'
        self._clicks: list[float] = []
        self.setStyleSheet(f'background: {BSOD_BG_11 if dark else BSOD_BG};')

        if not primary:
            return

        bg = BSOD_BG_11 if dark else BSOD_BG
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        # 所有内容用一个自绘 widget，方便按屏幕比例缩放
        self.panel = _BsodPanel(self, dark=dark, code=self.code)
        lay.addWidget(self.panel, 1)

    # 隐藏后门：在画面上快速连点 10 次鼠标，弹出解锁密码框
    # （孩子看到蓝屏只会以为电脑坏了，不会连着点 10 下）
    def mousePressEvent(self, ev):
        self._count_click(ev)

    def mouseDoubleClickEvent(self, ev):
        self._count_click(ev)

    def _count_click(self, ev):
        if ev.button() != Qt.LeftButton:
            return
        now = time.monotonic()
        self._clicks = [t for t in self._clicks if now - t <= CLICK_WINDOW]
        self._clicks.append(now)
        if len(self._clicks) >= CLICK_TARGET:
            self._clicks.clear()
            config.log(f'[backdoor] 检测到连点 {CLICK_TARGET} 次，弹出解锁框')
            if prompt_unlock(self):
                self.unlock_requested.emit()


class _BsodPanel(QWidget):
    """自绘蓝屏内容：:( + 提示语 + 进度 + 二维码 + 停止代码。"""

    def __init__(self, parent=None, dark: bool = False, code: str = ''):
        super().__init__(parent)
        self.dark = dark
        self.code = code or 'CRITICAL_PROCESS_DIED'
        self.qr = FakeQR(self, 96)
        self._tick = 0
        self._pct = 0
        t = QTimer(self)
        t.timeout.connect(self._step)
        t.start(900)

    def _step(self):
        self._tick += 1
        if self._pct < 100:
            self._pct = min(100, self._pct + 1)
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        W, H = self.width(), self.height()
        if W <= 0 or H <= 0:
            p.end()
            return

        # 自己画底色：父窗口的 QSS 背景会覆盖 paintEvent 内容，必须在此重绘
        p.fillRect(0, 0, W, H, QColor(BSOD_BG_11 if self.dark else BSOD_BG))

        big = W * 0.075

        fg = QColor('#ffffff')
        p.setPen(fg)

        x = int(W * 0.09)
        y = int(H * 0.20)

        # :(
        f = _font(int(big))
        p.setFont(f)
        p.drawText(x, y, ':)')

        # 主提示
        y += int(big * 1.5)
        f2 = _font(int(W * 0.0185))
        p.setFont(f2)
        p.drawText(x, y, '你的设备遇到问题，需要重新启动。我们只收集某些错误信息，然后为你重新启动。')
        y += int(W * 0.032)
        p.drawText(x, y, f'{self._pct}% 完成')

        # 二维码 + 说明
        qy = int(H * 0.60)
        qr = 96
        self.qr.setFixedSize(qr, qr)
        self.qr.move(x, qy)
        self.qr.show()

        tx = x + qr + int(W * 0.02)
        f3 = _font(int(W * 0.0128))
        p.setFont(f3)
        p.drawText(tx, qy + int(qr * 0.30),
                   '有关此问题的详细信息和可能的解决方法，请访问')
        p.drawText(tx, qy + int(qr * 0.30) + int(W * 0.019),
                   'https://www.windows.com/stopcode')
        p.drawText(tx, qy + int(qr * 0.30) + int(W * 0.052),
                   '如果致电支持人员，请向他们提供以下信息：')
        p.drawText(tx, qy + int(qr * 0.30) + int(W * 0.074),
                   f'停止代码: {self.code}')

        p.end()


class FakePopup(QWidget):
    """假的 Windows 错误弹窗：「您的电脑已损坏」。"""

    unlock_requested = pyqtSignal()

    def __init__(self, allow_close: bool = False):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Window)
        self.allow_close = allow_close
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.setWindowTitle('Microsoft Windows')
        self.setStyleSheet('QWidget#mask{background: #e9edf4;}')
        self._clicks: list[float] = []

        mask = QWidget(self)
        mask.setObjectName('mask')
        mask.setGeometry(self.rect())

        dlg = QFrame(mask)
        dlg.setStyleSheet('QFrame{background:#f0f0f0;border:1px solid #7c8a9e;}')
        dlg.setFixedWidth(430)

        v = QVBoxLayout(dlg)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        title = QLabel('  Microsoft Windows')
        title.setFixedHeight(30)
        title.setStyleSheet('background:#dfe4ec;color:#20304a;font-size:12.5px;'
                            'border-bottom:1px solid #c3cbd8;')
        v.addWidget(title)

        body = QWidget(dlg)
        bh = QHBoxLayout(body)
        bh.setContentsMargins(20, 20, 20, 8)
        bh.setSpacing(16)

        icon = QLabel('❌')
        icon.setStyleSheet('font-size:40px;')
        icon.setFixedWidth(52)
        icon.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        bh.addWidget(icon)

        txt = QLabel('您的电脑已损坏。\n\n'
                     '系统文件缺失或被篡改，无法继续使用。\n'
                     '请联系计算机维修人员处理。\n\n'
                     '错误代码: 0x80070057')
        txt.setWordWrap(True)
        txt.setStyleSheet('color:#16202e;font-size:13.5px;line-height:1.7;')
        bh.addWidget(txt, 1)
        v.addWidget(body)

        bar = QWidget(dlg)
        hh = QHBoxLayout(bar)
        hh.setContentsMargins(20, 8, 20, 16)
        hh.addStretch(1)
        self.ok = QPushButton('确定')
        self.ok.setFixedSize(92, 30)
        self.ok.setStyleSheet('QPushButton{background:#e6eaf1;border:1px solid #a8b3c4;'
                              'border-radius:3px;font-size:13px;}'
                              'QPushButton:pressed{background:#d3dae6;}')
        self.ok.clicked.connect(self._noop)
        hh.addWidget(self.ok)
        v.addWidget(bar)

        outer = QVBoxLayout(mask)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(dlg, 0, Qt.AlignCenter)

        self._mask = mask
        self._dlg = dlg

    def _noop(self):
        """点「确定」不关闭 —— 只会再弹一次（更像系统坏了）。"""
        self._dlg.setVisible(False)
        QTimer.singleShot(300, lambda: self._dlg.setVisible(True))

    def resizeEvent(self, ev):
        self._mask.setGeometry(self.rect())
        super().resizeEvent(ev)

    def mousePressEvent(self, ev):
        # 弹窗样式同样支持连点 10 次调出解锁框（点灰底空白区域）
        if ev.button() != Qt.LeftButton:
            return
        now = time.monotonic()
        self._clicks = [t for t in self._clicks if now - t <= CLICK_WINDOW]
        self._clicks.append(now)
        if len(self._clicks) >= CLICK_TARGET:
            self._clicks.clear()
            config.log(f'[backdoor] 弹窗样式：检测到连点 {CLICK_TARGET} 次')
            if prompt_unlock(self):
                self.unlock_requested.emit()

    def keyPressEvent(self, ev):
        ev.accept()

    def closeEvent(self, ev):
        if self.allow_close:
            ev.accept()
        else:
            ev.ignore()

    def show_over(self, screen):
        try:
            if self.windowHandle():
                self.windowHandle().setScreen(screen)
        except Exception:
            pass
        self.setGeometry(screen.geometry())
        self.showFullScreen()
        self.raise_()


class LockManager(QObject):
    """管理所有屏幕的锁定画面，并在解锁后清理。"""

    unlocked = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.windows: list[QWidget] = []
        self._locked = False
        self._style = 'bsod'
        self._keep = QTimer(self)
        self._keep.setInterval(900)
        self._keep.timeout.connect(self._raise_all)

    @property
    def is_locked(self) -> bool:
        return self._locked

    def lock(self, style: str = 'bsod', code: str = 'CRITICAL_PROCESS_DIED') -> None:
        if self._locked:
            return
        self._locked = True
        self._style = style
        screens = QApplication.screens() or []
        primary = QApplication.primaryScreen()

        for i, scr in enumerate(screens):
            is_primary = (scr is primary) or (i == 0)
            if style == 'popup':
                w: QWidget = FakePopup()
            else:
                w = BsodScreen(primary=is_primary, code=code)
            if hasattr(w, 'unlock_requested'):
                w.unlock_requested.connect(self._on_local_unlock)
            w.show_over(scr)
            self.windows.append(w)

        if not screens:
            w = BsodScreen(primary=True, code=code)
            w.unlock_requested.connect(self._on_local_unlock)
            w.setGeometry(0, 0, 1280, 800)
            w.show()
            self.windows.append(w)

        self._keep.start()
        config.log(f'[lock] 已锁定（样式={style}）')

    def _raise_all(self):
        if not self._locked:
            return
        # 密码框弹出期间绝对不能抢焦点，否则会把对话框压回蓝屏下面
        if QApplication.activeModalWidget() is not None:
            return
        for w in self.windows:
            try:
                w.raise_()
                w.activateWindow()
            except Exception:
                pass

    def _on_local_unlock(self):
        self.unlocked.emit()
        QTimer.singleShot(60, self.unlock)

    def unlock(self) -> None:
        if not self._locked:
            return
        self._locked = False
        self._keep.stop()
        for w in self.windows:
            try:
                w.allow_close = True
                w.hide()
                w.deleteLater()
            except Exception:
                pass
        self.windows = []
        config.log('[lock] 已解除锁定')
