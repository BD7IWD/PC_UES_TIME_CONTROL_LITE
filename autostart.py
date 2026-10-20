# -*- coding: utf-8 -*-
"""开机自启动（写当前用户注册表 Run 键，不需要管理员权限）。

命令行用法：
    python autostart.py enable
    python autostart.py disable
    python autostart.py status

作者：野怼怼；https://www.bd7iwd.com
许可：MIT
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    import winreg
except ImportError:  # 非 Windows
    winreg = None

RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
VALUE_NAME = 'PCTimeControlLite'


def _launch_command() -> str:
    """返回写入注册表的启动命令。"""
    if getattr(sys, 'frozen', False):
        return f'"{Path(sys.executable).resolve()}"'

    base = Path(__file__).resolve().parent
    main_py = base / 'main.py'
    exe = Path(sys.executable)
    pyw = exe.with_name('pythonw.exe')
    launcher = pyw if pyw.exists() else exe
    return f'"{launcher}" "{main_py}"'


def is_enabled() -> bool:
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as k:
            val, _ = winreg.QueryValueEx(k, VALUE_NAME)
            return bool(val)
    except FileNotFoundError:
        return False
    except OSError:
        return False


def enable() -> bool:
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, VALUE_NAME, 0, winreg.REG_SZ, _launch_command())
        return True
    except OSError:
        return False


def disable() -> bool:
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, VALUE_NAME)
        return True
    except FileNotFoundError:
        return True
    except OSError:
        return False


if __name__ == '__main__':
    cmd = (sys.argv[1] if len(sys.argv) > 1 else 'status').lower()
    if cmd == 'enable':
        print('已开启开机自启动' if enable() else '开启失败')
    elif cmd == 'disable':
        print('已关闭开机自启动' if disable() else '关闭失败')
    else:
        print('当前状态:', '已开启' if is_enabled() else '未开启')
        print('启动命令:', _launch_command())
