# -*- coding: utf-8 -*-
"""儿童电脑使用时长控制 · 单机版

一个 exe 全搞定：内置 Web 服务（手机访问 电脑IP:8080）+ 托盘客户端 + 计时 + 假蓝屏。
不需要服务器、不需要数据库、不需要联网。

用法：
    python main.py
    python main.py --watchdog N    守护模式（内部使用）
    python main.py --port 8080     临时改端口

作者：野怼怼；https://www.bd7iwd.com
许可：MIT
"""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from PyQt5.QtCore import QObject, Qt, QTimer, QSharedMemory, QUrl, pyqtSignal
from PyQt5.QtGui import QColor, QDesktopServices, QIcon, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import (QAction, QApplication, QInputDialog, QLineEdit, QMenu,
                             QMessageBox, QSystemTrayIcon)

sys.path.insert(0, str(Path(__file__).resolve().parent))

import autostart
from core import config, netinfo, store
from core.guard import KeyboardGuard, pid_alive
from ui.lock_screen import LockManager
from ui.toast import ToastManager
from web.server import WebService

DETACHED = 0x00000008


# ------------------------------------------------------------------ 图标

def _bundled_icon_path() -> Path | None:
    """app.ico 的位置：打包后在 _MEIPASS，源码运行时在项目根目录。"""
    candidates = []
    mei = getattr(sys, '_MEIPASS', '')
    if mei:
        candidates.append(Path(mei) / 'app.ico')
    candidates.append(Path(__file__).resolve().parent / 'app.ico')
    for p in candidates:
        if p.exists():
            return p
    return None


def make_icon(color: str, size: int = 64, badge: bool = False) -> QIcon:
    """托盘图标：优先用 app.ico（与 exe 图标一致），找不到再画圆点兜底。

    badge=True 时在右下角叠一个小圆点，用来表达「已锁定」等状态。
    """
    p = _bundled_icon_path()
    if p is not None:
        ic = QIcon(str(p))
        if not ic.isNull():
            pm = ic.pixmap(32, 32)
            if badge:
                painter = QPainter(pm)
                painter.setRenderHint(QPainter.Antialiasing)
                painter.setPen(QPen(QColor('#ffffff'), 1.5))
                painter.setBrush(QColor(color))
                r = 7
                painter.drawEllipse(32 - r * 2 - 1, 32 - r * 2 - 1, r * 2, r * 2)
                painter.end()
            return QIcon(pm)

    # 兜底：纯色圆 + 白色指针
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    pnt = QPainter(pm)
    pnt.setRenderHint(QPainter.Antialiasing)
    pnt.setPen(Qt.NoPen)
    pnt.setBrush(QColor(color))
    pnt.drawEllipse(2, 2, size - 4, size - 4)
    pen = QPen(QColor('#ffffff'))
    pen.setWidth(max(3, size // 14))
    pen.setCapStyle(Qt.RoundCap)
    pnt.setPen(pen)
    c = size / 2
    pnt.drawLine(int(c), int(c), int(c), int(c * 0.40))
    pnt.drawLine(int(c), int(c), int(c * 0.74), int(c * 0.62))
    pnt.end()
    return QIcon(pm)


def fmt_dur(sec: int) -> str:
    sec = max(0, int(sec))
    hh, mm, ss = sec // 3600, (sec % 3600) // 60, sec % 60
    if hh:
        return f'{hh}小时{mm}分'
    if mm:
        return f'{mm}分{ss}秒'
    return f'{ss}秒'


# ------------------------------------------------------------------ 主控制器

class App(QObject):
    def __init__(self, qapp: QApplication):
        super().__init__()
        self.qapp = qapp
        self.cfg = config.load_cfg()

        # 组件
        self.web = WebService()
        self.locker = LockManager()
        self.locker.unlocked.connect(self._on_local_unlocked)
        self.guard = KeyboardGuard()
        self.guard.start()
        self.toasts = ToastManager()

        # 状态
        self.settings = store.get_settings()
        self._cfg_ver = self.settings.get('updated_at', '')
        self.quota = max(60, int(self.settings['quota_minutes']) * 60)
        self.used = store.get_used()
        self.pending = 0
        self.remaining = max(0, self.quota - self.used)
        self._cur_date = store.today()
        self._tick_n = 0
        self._written = self.used   # 最后一次成功写入 DB 的用量

        # 托盘
        self.icon_ok = make_icon('#18a058')
        self.icon_lock = make_icon('#d1373a', badge=True)
        self.tray = QSystemTrayIcon(self.icon_ok)
        self.tray.setToolTip(config.APP_TITLE)
        self._build_menu()
        self.tray.activated.connect(self._on_tray_click)

        # 定时器
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.tick)

    # ------------------------------------------------------------ 启动

    def start(self) -> None:
        config.log(f'[app] 启动 v{config.APP_VER} data={config.DATA_DIR}')
        ok = self.web.start()
        if not ok:
            self.tray.showMessage('网页服务启动失败',
                                  f'端口 {self.web.port} 可能被占用，手机将无法访问。',
                                  QSystemTrayIcon.Critical, 10000)

        self.tray.show()
        self.tick()
        self.timer.start()

        url = netinfo.access_urls(self.web.port)[0]
        if not store.is_initialized():
            self.tray.showMessage('还差一步',
                                  f'请用手机连同一个 Wi-Fi，打开 {url} 完成设置。',
                                  QSystemTrayIcon.Information, 15000)
        else:
            self.tray.showMessage('管控已启动',
                                  f'手机访问 {url} 查看和调整使用时间。',
                                  QSystemTrayIcon.Information, 8000)

        store.add_event('started', f'程序启动 v{config.APP_VER}')

        try:
            if not autostart.is_enabled():
                autostart.enable()
            self.act_auto.setChecked(autostart.is_enabled())
        except Exception:
            pass

        if str(self.cfg.get('watchdog', 1)) == '1':
            spawn_watchdog()

    def shutdown(self) -> None:
        try:
            if self.pending:
                store.add_used(self.pending)
                self.pending = 0
            store.add_event('stopped', '家长退出程序')
        except Exception:
            pass
        try:
            self.web.stop()
        except Exception:
            pass
        try:
            self.guard.set_active(False)
            self.guard.stop()
        except Exception:
            pass

    # ------------------------------------------------------------ 菜单

    def _build_menu(self) -> None:
        m = QMenu()
        self.act_state = QAction('状态：--', m)
        self.act_state.setEnabled(False)
        m.addAction(self.act_state)

        self.act_url = QAction('手机访问：--', m)
        self.act_url.setEnabled(False)
        m.addAction(self.act_url)

        act_open = QAction('在本机打开管理页', m)
        act_open.triggered.connect(self._open_page)
        m.addAction(act_open)
        m.addSeparator()

        self.act_auto = QAction('开机自动启动', m)
        self.act_auto.setCheckable(True)
        self.act_auto.triggered.connect(self._toggle_autostart)
        m.addAction(self.act_auto)

        act_log = QAction('打开数据目录', m)
        act_log.triggered.connect(lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(config.DATA_DIR))))
        m.addAction(act_log)
        m.addSeparator()

        act_exit = QAction('退出（需要解锁密码）', m)
        act_exit.triggered.connect(self._ask_exit)
        m.addAction(act_exit)

        self.tray.setContextMenu(m)
        self.menu = m

    def _open_page(self) -> None:
        QDesktopServices.openUrl(QUrl(f'http://127.0.0.1:{self.web.port}/'))

    def _toggle_autostart(self, checked: bool) -> None:
        ok = autostart.enable() if checked else autostart.disable()
        if not ok:
            self.tray.showMessage('设置失败', '无法修改开机启动项',
                                  QSystemTrayIcon.Warning, 5000)
        self.act_auto.setChecked(autostart.is_enabled())

    def _on_tray_click(self, reason) -> None:
        if reason == QSystemTrayIcon.DoubleClick:
            self._open_page()

    def _ask_exit(self) -> None:
        s = store.get_settings()
        if s.get('unlock_hash'):
            pwd, ok = QInputDialog.getText(None, '退出管控', '请输入解锁密码：', QLineEdit.Password)
            if not ok:
                return
            if not store.verify_pwd(pwd, s['unlock_hash']):
                QMessageBox.warning(None, '密码错误', '密码不正确，无法退出。')
                return
        config.log('[app] 家长退出')
        self.shutdown()
        kill_watchdog()          # 先干掉守护，否则它会立刻把我们拉起来
        self.tray.hide()
        QApplication.quit()

    # ------------------------------------------------------------ 每秒

    def tick(self) -> None:
        try:
            self._tick_n += 1
            self._sync_settings()
            self._reconcile_used()
            s = self.settings
            enabled = int(s['enabled']) == 1
            locked_flag = int(s['locked']) == 1

            # 跨天
            d = store.today()
            if d != self._cur_date:
                self._cur_date = d
                self.pending = 0
                self.used = store.get_used(d)
                config.log(f'[app] 新的一天 {d}')

            # 计时
            if enabled and not self.locker.is_locked:
                self.pending += 1

            # 落盘（每 5 秒或进入锁定前）
            if self.pending >= 5:
                self.used = store.add_used(self.pending)
                self._written = self.used
                self.pending = 0

            self.remaining = max(0, self.quota - self.used - self.pending)

            # 状态机：手动锁定无条件生效；时间到只在计时中才锁
            should_lock = locked_flag or (enabled and self.remaining <= 0)
            if should_lock and not self.locker.is_locked:
                self.do_lock('manual' if locked_flag else 'quota')
            elif not should_lock and self.locker.is_locked:
                self.locker.unlock()

            # 时间到 → 直接锁定（不做任何提前提醒）
            self.handle_commands()

            self.update_tray()
        except Exception as e:
            config.log(f'[tick] 异常: {e}')

    def _sync_settings(self) -> None:
        s = store.get_settings()
        ver = s.get('updated_at', '')
        if ver == self._cfg_ver:
            return
        self._cfg_ver = ver
        self.settings = s
        self.quota = max(60, int(s['quota_minutes']) * 60)
        self.remaining = max(0, self.quota - self.used - self.pending)
        config.log(f'[cfg] 设置更新 quota={self.quota}s '
                   f'style={s.get("lock_style")} enabled={s["enabled"]}')

    def _reconcile_used(self) -> None:
        """跟数据库对账：家长在手机上「重置/解锁」会把 used 清零，这里要认。"""
        db_used = store.get_used()
        if db_used + 2 < self._written:
            config.log(f'[sync] 检测到外部重置：{self._written}s → {db_used}s')
            self.used = db_used
            self.pending = 0
            self._written = db_used
        elif db_used > self._written:
            # 别的窗口/进程写入得更多（例如断点恢复），以大的为准
            self.used = db_used
            self._written = db_used

    # ------------------------------------------------------------ 锁定

    def do_lock(self, reason: str) -> None:
        if self.locker.is_locked:
            return
        if self.pending:
            self.used = store.add_used(self.pending)
            self.pending = 0
        self.guard.set_active(True)
        s = self.settings
        self.locker.lock(s.get('lock_style', 'bsod'),
                         s.get('bsod_code') or 'CRITICAL_PROCESS_DIED')
        # 把锁定状态写回数据库，手机端首页才能显示「已锁定」
        try:
            store.update_settings(locked=1, lock_reason=reason)
        except Exception:
            pass
        self.tray.setIcon(self.icon_lock)
        store.add_event('locked', '时间用完，进入锁定画面' if reason == 'quota' else '手机端点了锁定')
        self.update_tray()

    def _on_local_unlocked(self) -> None:
        self.guard.set_active(False)
        self.used = 0
        self.pending = 0
        self.remaining = self.quota
        self.tray.setIcon(self.icon_ok)
        self.update_tray()

    # ------------------------------------------------------------ 指令

    def handle_commands(self) -> None:
        for cmd in store.take_commands():
            t = cmd.get('type')
            pl = cmd.get('payload') or {}
            if t == 'toast':
                text = str(pl.get('text') or '').strip()
                if text:
                    config.log(f'[cmd] 手机提醒: {text}')
                    self.toasts.show(text, int(pl.get('seconds') or 10),
                                     'warn' if pl.get('level') == 'warn' else 'info')
                    try:
                        self.tray.showMessage('📢 家长提醒', text, QSystemTrayIcon.Information, 8000)
                    except Exception:
                        pass
            elif t == 'lock':
                store.update_settings(locked=1, lock_reason='manual')
            elif t == 'unlock':
                store.update_settings(locked=0, lock_reason=None)
                store.reset_used()

    # ------------------------------------------------------------ 托盘文字

    def update_tray(self) -> None:
        try:
            urls = netinfo.access_urls(self.web.port)
            if self.locker.is_locked:
                st = '状态：已锁定（蓝屏中）'
            elif int(self.settings['enabled']) != 1:
                st = '状态：待机（未开始计时）'
            else:
                st = f'状态：计时中 · 剩余 {fmt_dur(self.remaining)}'
            self.act_state.setText(st)
            self.act_url.setText(f'手机访问：{urls[0]}')
            self.tray.setToolTip(f'{config.APP_TITLE} — {st}')
        except Exception:
            pass


# ------------------------------------------------------------------ Watchdog

def watchdog_running() -> bool:
    try:
        p = int(config.WD_PID.read_text(encoding='utf-8').strip())
        return pid_alive(p) and p != os.getpid()
    except Exception:
        return False


def kill_watchdog() -> None:
    """家长主动退出时，必须先把守护进程杀掉，否则它会把程序又拉起来。"""
    try:
        pid = int(config.WD_PID.read_text(encoding='utf-8').strip())
    except Exception:
        return
    if not pid or pid == os.getpid():
        return
    try:
        subprocess.run(['taskkill', '/PID', str(pid), '/F'],
                       capture_output=True, timeout=5)
        config.log(f'[watchdog] 已停止守护进程 pid={pid}')
    except Exception as e:
        config.log(f'[watchdog] 停止失败: {e}')
    try:
        config.WD_PID.unlink()
    except Exception:
        pass


def cleanup_stale_meipass() -> None:
    """清理 TEMP 下超过 24 小时的 _MEI 解压残留。

    PyInstaller onefile 每次启动都会解压到 %TEMP%\\_MEIxxxxx。
    进程被强杀时这个目录不会删，攒多了之后启动器清理孤儿目录会和
    新实例的解压打架，报「Failed to import encodings module」。
    """
    if not getattr(sys, 'frozen', False):
        return
    import tempfile
    tmp = tempfile.gettempdir()
    cur = os.path.abspath(getattr(sys, '_MEIPASS', '') or '')
    now = time.time()
    removed = 0
    for p in glob.glob(os.path.join(tmp, '_MEI*')):
        if not os.path.isdir(p):
            continue
        if cur and os.path.abspath(p) == cur:
            continue
        try:
            if now - os.path.getmtime(p) < 86400:
                continue
            shutil.rmtree(p, ignore_errors=True)
            removed += 1
        except Exception:
            pass
    if removed:
        config.log(f'[app] 清理了 {removed} 个过期的 _MEI 解压残留目录')


def spawn_watchdog() -> None:
    if watchdog_running():
        return
    base = config.app_dir()
    if getattr(sys, 'frozen', False):
        args = [sys.executable, '--watchdog', str(os.getpid())]
    else:
        exe = Path(sys.executable)
        pyw = exe.with_name('pythonw.exe')
        args = [str(pyw if pyw.exists() else exe), str(base / 'main.py'),
                '--watchdog', str(os.getpid())]
    try:
        subprocess.Popen(args, cwd=str(base), creationflags=DETACHED,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
        config.log('[watchdog] 已启动')
    except Exception as e:
        config.log(f'[watchdog] 启动失败: {e}')


def run_watchdog(pid: int) -> None:
    base = config.app_dir()
    try:
        config.WD_PID.write_text(str(os.getpid()), encoding='utf-8')
    except Exception:
        pass
    config.log(f'[watchdog] 守护 target={pid}')
    if getattr(sys, 'frozen', False):
        args = [sys.executable]
    else:
        exe = Path(sys.executable)
        pyw = exe.with_name('pythonw.exe')
        args = [str(pyw if pyw.exists() else exe), str(base / 'main.py')]

    target = pid
    fails = 0
    while True:
        time.sleep(3)
        if target and not pid_alive(target):
            # 给旧进程留一点时间彻底释放文件句柄，否则新实例解压可能撞车
            time.sleep(1.2)
            config.log('[watchdog] 主进程已退出，重新拉起')
            try:
                p = subprocess.Popen(args, cwd=str(base), creationflags=DETACHED,
                                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
                target = p.pid
            except Exception as e:
                config.log(f'[watchdog] 拉起失败: {e}')
                target = 0
                continue

            # 熔断：连续 3 次拉起后都活不过 4 秒，说明有别的实例占着或环境异常，
            # 继续拉只会变成死循环，直接放弃。
            time.sleep(4)
            if not pid_alive(target):
                fails += 1
                config.log(f'[watchdog] 新进程未能存活（第 {fails} 次）')
                if fails >= 3:
                    config.log('[watchdog] 连续失败，守护进程退出')
                    break
                target = 0
            else:
                fails = 0


# ------------------------------------------------------------------ 入口

def main() -> int:
    if '--watchdog' in sys.argv:
        try:
            i = sys.argv.index('--watchdog')
            pid = int(sys.argv[i + 1])
        except Exception:
            pid = 0
        run_watchdog(pid)
        return 0

    # 允许命令行改端口
    if '--port' in sys.argv:
        try:
            i = sys.argv.index('--port')
            cfg = config.load_cfg()
            cfg['port'] = int(sys.argv[i + 1])
            config.save_cfg(cfg)
        except Exception:
            pass

    cleanup_stale_meipass()      # 尽早清理，减少启动器清理孤儿目录的压力

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setApplicationName(config.APP_NAME)
    app.setQuitOnLastWindowClosed(False)

    shm = QSharedMemory('PCTimeLite_SingleInstance')
    if not shm.create(1):
        config.log('[app] 已有实例在运行')
        return 0

    ctrl = App(app)
    app._ctrl = ctrl
    ctrl.start()
    return app.exec_()


if __name__ == '__main__':
    sys.exit(main())
