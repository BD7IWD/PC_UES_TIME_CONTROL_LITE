# -*- coding: utf-8 -*-
"""Windows 底层守卫：全局键盘钩子（锁屏期间屏蔽快捷键）、进程存活检测。

全部使用 ctypes，无需 pywin32。

作者：野怼怼；https://www.bd7iwd.com
许可：MIT
"""
from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes

from . import config

user32 = ctypes.WinDLL('user32', use_last_error=True)
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_QUIT = 0x0012

VK_TAB = 0x09
VK_ESCAPE = 0x1B
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12          # Alt
VK_F4 = 0x73
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_DELETE = 0x2E


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ('vkCode', wintypes.DWORD),
        ('scanCode', wintypes.DWORD),
        ('flags', wintypes.DWORD),
        ('time', wintypes.DWORD),
        ('dwExtraInfo', ctypes.c_size_t),
    ]


HOOKPROC = ctypes.CFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

# ⚠️ 64 位下必须显式声明 restype/argtypes，否则句柄被截断成 32 位，
#    SetWindowsHookExW 会返回 126 (ERROR_MOD_NOT_FOUND) 而静默失败。
user32.SetWindowsHookExW.restype = ctypes.c_void_p
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, ctypes.c_void_p, wintypes.DWORD]
user32.CallNextHookEx.restype = ctypes.c_ssize_t
user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL
user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.PostThreadMessageW.restype = wintypes.BOOL
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.GetMessageW.restype = ctypes.c_int
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), ctypes.c_void_p, wintypes.UINT, wintypes.UINT]
user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]

kernel32.GetModuleHandleW.restype = ctypes.c_void_p
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.OpenProcess.restype = ctypes.c_void_p
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.GetExitCodeProcess.restype = wintypes.BOOL
kernel32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [ctypes.c_void_p]


class KeyboardGuard(threading.Thread):
    """低级键盘钩子。set_active(True) 后开始吞掉危险快捷键。

    屏蔽：Win / Alt+Tab / Alt+Esc / Alt+F4 / Ctrl+Esc / Ctrl+Shift+Esc / Win+R、D、E、L ...
    （Ctrl+Alt+Del 是系统安全序列，用户态无法屏蔽）
    """

    def __init__(self) -> None:
        super().__init__(daemon=True, name='KeyboardGuard')
        self._active = False
        self._stop_flag = False
        self._hook = None
        self._tid: int | None = None
        self._proc = HOOKPROC(self._callback)  # 保持引用，防止被 GC

    # ---- 外部接口 ----
    def set_active(self, on: bool) -> None:
        self._active = bool(on)

    def stop(self) -> None:
        self._stop_flag = True
        if self._tid:
            try:
                user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)
            except Exception:
                pass

    # ---- 线程体 ----
    def run(self) -> None:
        try:
            self._tid = kernel32.GetCurrentThreadId()
            hmod = kernel32.GetModuleHandleW(None)
            self._hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, hmod, 0)
            if not self._hook:
                config.log(f'[guard] 键盘钩子安装失败 err={ctypes.get_last_error()}')
                return
            config.log('[guard] 键盘钩子已安装')
            msg = wintypes.MSG()
            while not self._stop_flag:
                ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if ret is None or ret == 0 or ret == -1:
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        except Exception as e:
            config.log(f'[guard] 异常: {e}')
        finally:
            if self._hook:
                try:
                    user32.UnhookWindowsHookEx(self._hook)
                except Exception:
                    pass
                self._hook = None

    # ---- 钩子回调 ----
    def _callback(self, n_code, w_param, l_param):
        try:
            if n_code == 0 and self._active:
                kb = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                vk = int(kb.vkCode)
                is_down = w_param in (WM_KEYDOWN, WM_SYSKEYDOWN)

                # Win 键自身（覆盖 Win+D / Win+R / Win+L / Win+E 等全部组合）
                if vk in (VK_LWIN, VK_RWIN):
                    return 1

                if is_down:
                    alt = bool(user32.GetAsyncKeyState(VK_MENU) & 0x8000)
                    ctrl = bool(user32.GetAsyncKeyState(VK_CONTROL) & 0x8000)
                    # Alt+Tab / Alt+Esc / Alt+F4
                    if alt and vk in (VK_TAB, VK_ESCAPE, VK_F4):
                        return 1
                    # Ctrl+Esc / Ctrl+Shift+Esc（任务管理器）
                    if ctrl and vk == VK_ESCAPE:
                        return 1
                    # Ctrl+Alt+Del 无法拦，但 Ctrl+Shift+Del 之类也一并吞掉
                    if ctrl and vk == VK_DELETE:
                        return 1
        except Exception:
            pass
        return user32.CallNextHookEx(None, n_code, w_param, l_param)


# ---------------------------------------------------------------- 进程工具

def pid_alive(pid: int) -> bool:
    """判断进程是否还活着（不用 tasklist，避免弹黑框）。"""
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    try:
        h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not h:
            return False
        code = wintypes.DWORD()
        ok = kernel32.GetExitCodeProcess(h, ctypes.byref(code))
        kernel32.CloseHandle(h)
        return bool(ok) and code.value == STILL_ACTIVE
    except Exception:
        return False
