# -*- coding: utf-8 -*-
"""单机版端到端：时间耗尽 → 直接蓝屏（无任何提醒）→ 手机解锁恢复。

作者：野怼怼；https://www.bd7iwd.com
许可：MIT
"""
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from http.cookiejar import CookieJar
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path.home() / 'AppData' / 'Local' / 'PCTimeControlLite'
DB = DATA / 'data.db'
LOG = DATA / 'client.log'
BASE = 'http://127.0.0.1:8080'
TODAY = date.today().isoformat()

cj = CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
ok = True


def check(name, cond, extra=''):
    global ok
    print(('  PASS  ' if cond else '  FAIL  ') + name + (('  -> ' + str(extra)) if extra and not cond else ''))
    if not cond:
        ok = False


def get(p):
    with opener.open(BASE + p, timeout=15) as r:
        return r.read().decode('utf-8', 'replace')


def post(p, d):
    with opener.open(BASE + p, urllib.parse.urlencode(d).encode(), timeout=15) as r:
        return r.read().decode('utf-8', 'replace')


def set_used_db(sec):
    c = sqlite3.connect(str(DB), timeout=15)
    try:
        c.execute('INSERT INTO usage (stat_date, used_seconds, updated_at) VALUES (?,?,?) '
                  'ON CONFLICT(stat_date) DO UPDATE SET used_seconds = ?, updated_at = ?',
                  (TODAY, int(sec), time.strftime('%Y-%m-%d %H:%M:%S'),
                   int(sec), time.strftime('%Y-%m-%d %H:%M:%S')))
        c.commit()
    finally:
        c.close()


def db_used():
    c = sqlite3.connect(str(DB), timeout=15)
    try:
        row = c.execute('SELECT used_seconds FROM usage WHERE stat_date = ?', (TODAY,)).fetchone()
        return int(row[0]) if row else 0
    finally:
        c.close()


def log_from(off):
    with open(LOG, 'r', encoding='utf-8', errors='replace') as f:
        f.seek(off)
        return f.read()


def wait_log(mark, needle, tries=20, step=1):
    for i in range(tries):
        time.sleep(step)
        if needle in log_from(mark):
            return i + 1
    return 0


print('=== 准备：登录并设为 2 分钟额度 + 开始管控 ===')
get('/login')
post('/login', {'pwd': 'admin123'})
post('/settings', {'quota': '2', 'style': 'bsod'})
post('/start', {})
time.sleep(3)
check('额度已设为 2 分钟且用时已清零', db_used() <= 3, db_used())

print('=== 1. 时间耗尽 → 直接蓝屏，全程无任何提醒 ===')
mark = LOG.stat().st_size if LOG.exists() else 0
set_used_db(125)
sec = wait_log(mark, '[lock] 已锁定', 15)
check('客户端自动进入锁定画面', sec > 0, log_from(mark)[-300:])
if sec:
    print(f'  第 {sec} 秒进入锁定')

txt = log_from(mark)
check('没有任何「x分钟后关机」提醒', '分钟后关机' not in txt, txt[-300:])
check('没有「时间已到」类提示', '时间已到' not in txt and '今日时间已到' not in txt, txt[-200:])

html = get('/')
check('手机端显示已锁定', '已锁定' in html, html[:300])

print('=== 2. 手机端点解除锁定 → 恢复并清零 ===')
mark2 = LOG.stat().st_size if LOG.exists() else 0
post('/unlock', {})
sec = wait_log(mark2, '[lock] 已解除锁定', 15)
check('客户端恢复可用', sec > 0, log_from(mark2)[-300:])
time.sleep(1)
check('今日已用时间已清零', db_used() <= 3, db_used())

html = get('/')
check('手机端显示正常', '正常使用' in html or '已用' in html, html[:300])

print('=== 3. 暂停管控后不再锁定 ===')
post('/pause', {})
time.sleep(2)
mark3 = LOG.stat().st_size if LOG.exists() else 0
set_used_db(999)
time.sleep(4)
check('暂停状态下不锁屏', '[lock] 已锁定' not in log_from(mark3), log_from(mark3)[-200:])

print('=== 清理：恢复 120 分钟额度并回到待机 ===')
post('/settings', {'quota': '120', 'style': 'bsod'})
post('/pause', {})

print()
print('=== 全部通过 ===' if ok else '=== 存在失败项 ===')
sys.exit(0 if ok else 1)
