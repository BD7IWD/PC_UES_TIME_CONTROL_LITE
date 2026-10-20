# -*- coding: utf-8 -*-
"""验证「连点 10 次」后门：9 次不触发，第 10 次触发；超时不累计。

作者：野怼怼；https://www.bd7iwd.com
许可：MIT
"""
import os
import sys
import time
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PyQt5.QtCore import QPoint, Qt  # noqa: E402
from PyQt5.QtTest import QTest  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

import ui.lock_screen as ls  # noqa: E402

app = QApplication(sys.argv)
ok = True


def check(name, cond, extra=''):
    global ok
    print(('  PASS  ' if cond else '  FAIL  ') + name + (('  -> ' + str(extra)) if extra and not cond else ''))
    if not cond:
        ok = False


calls = []
_orig = ls.prompt_unlock
ls.prompt_unlock = lambda parent=None: (calls.append(1), False)[1]   # 桩：只记录，不弹窗


def click_n(widget, n, gap_ms=30):
    for _ in range(n):
        QTest.mouseClick(widget, Qt.LeftButton, pos=QPoint(400, 300))
        QTest.qWait(gap_ms)


print('=== 常量 ===')
check('CLICK_TARGET == 10', ls.CLICK_TARGET == 10, ls.CLICK_TARGET)
check('时间窗口 > 0', ls.CLICK_WINDOW > 0, ls.CLICK_WINDOW)

print('=== 蓝屏样式 ===')
calls.clear()
w = ls.BsodScreen(primary=True)
w.resize(800, 600)
w.show()
app.processEvents()

click_n(w, 9)
check('连点 9 次不触发', len(calls) == 0, len(calls))

click_n(w, 1)
check('第 10 次触发解锁框', len(calls) == 1, len(calls))

calls.clear()
click_n(w, 10)
check('可再次触发（计数已重置）', len(calls) == 1, len(calls))

print('=== 间隔超时不累计 ===')
calls.clear()
w._clicks = [time.monotonic() - 99]   # 塞一个很久以前的点击
click_n(w, 9, gap_ms=10)
check('旧点击被清理，9 次仍不触发', len(calls) == 0, len(calls))
w.close()

print('=== 假弹窗样式 ===')
calls.clear()
p = ls.FakePopup()
p.setGeometry(0, 0, 800, 600)
p.show()
app.processEvents()
click_n(p, 9)
check('弹窗样式连点 9 次不触发', len(calls) == 0, len(calls))
click_n(p, 1)
check('弹窗样式第 10 次触发', len(calls) == 1, len(calls))
p.close()

ls.prompt_unlock = _orig

print()
print('=== 全部通过 ===' if ok else '=== 存在失败项 ===')
sys.exit(0 if ok else 1)
