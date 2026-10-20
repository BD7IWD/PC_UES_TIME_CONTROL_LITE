# -*- coding: utf-8 -*-
"""单机版 Web 端全流程测试：首次设置 → 登录 → 各项操作 → 客户端真实响应。

作者：野怼怼；https://www.bd7iwd.com
许可：MIT
"""
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = Path.home() / 'AppData' / 'Local' / 'PCTimeControlLite' / 'client.log'
BASE = 'http://127.0.0.1:8080'

cj = CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
ok = True


def check(name, cond, extra=''):
    global ok
    print(('  PASS  ' if cond else '  FAIL  ') + name + (('  -> ' + str(extra)) if extra and not cond else ''))
    if not cond:
        ok = False


def get(path):
    with opener.open(BASE + path, timeout=15) as r:
        return r.read().decode('utf-8', 'replace'), r.status


def post(path, data):
    body = urllib.parse.urlencode(data).encode('utf-8')
    with opener.open(BASE + path, body, timeout=15) as r:
        return r.read().decode('utf-8', 'replace'), r.status


def post_raw(path, data):
    """带 cookie 但不抛异常，用来测 401/403/404。"""
    body = urllib.parse.urlencode(data).encode('utf-8')
    req = urllib.request.Request(BASE + path, data=body, method='POST')
    try:
        with opener.open(req, timeout=15) as r:
            return r.read().decode('utf-8', 'replace'), r.status
    except urllib.error.HTTPError as e:
        return e.read().decode('utf-8', 'replace'), e.code


def log_from(off):
    with open(LOG, 'r', encoding='utf-8', errors='replace') as f:
        f.seek(off)
        return f.read()


print('=== 1. 未初始化时强制进入设置向导 ===')
html, code = get('/')
check('GET / 返回首次设置页', '首次使用' in html, html[:150])

print('=== 2. 完成首次设置 ===')
html, code = post('/setup', {'admin_pwd': 'admin123', 'unlock_pwd': '888888', 'quota': '120'})
check('设置后进入总览', '今日剩余' in html and '快捷操作' in html, html[:200])
check('显示手机访问地址', '192.168' in html or '127.0.0.1' in html)

print('=== 3. 各页面可渲染 ===')
for path, kw in [('/', '今日剩余'), ('/settings', '时间设置'), ('/logs', '事件记录')]:
    html, code = get(path)
    bad = ('Traceback' in html) or ('服务内部错误' in html)
    check(f'GET {path} 正常', code == 200 and kw in html and not bad, html[:200])

print('=== 4. 修改额度为 2 分钟 ===')
html, _ = post('/settings', {'quota': '2', 'style': 'bsod'})
check('设置已保存', '设置已保存' in html, html[:150])
html, _ = get('/')
check('首页反映 2 分钟额度', '2分' in html or '0:0' in html, html[:300])

print('=== 4b. 开始 / 暂停管控（新增开关）===')
html, _ = post('/start', {})
check('开始后按钮变为「暂停管控」', '暂停管控' in html, html[:300])
check('开始后不再显示开始按钮', 'action="/start"' not in html)
html, _ = get('/')
check('首页处于计时状态', '暂停管控' in html and '待机中' not in html, html[:300])
html, _ = post('/pause', {})
check('暂停后进入待机', '待机中' in html, html[:300])
check('出现「开始管控」按钮', '开始管控' in html)
html, _ = get('/')
check('首页显示待机中', '待机中' in html and '开始管控' in html, html[:300])
html, _ = post('/start', {})
check('可再次开始', '暂停管控' in html, html[:300])

print('=== 5. 发送提醒 ===')
post('/toast', {'text': '该写作业了'})
html, _ = get('/logs')
check('提醒记录已写入', '该写作业了' in html, html[:200])

print('=== 6. 手机端点「立即锁定」→ 客户端真的蓝屏 ===')
mark = LOG.stat().st_size if LOG.exists() else 0
post('/lock', {})
locked = False
for i in range(20):
    time.sleep(1)
    if '[lock] 已锁定' in log_from(mark):
        locked = True
        print(f'  客户端在第 {i+1} 秒锁定')
        break
check('客户端进入锁定画面', locked, log_from(mark)[-300:])

html, _ = get('/')
check('手机端显示已锁定', '已锁定' in html, html[:300])

print('=== 7. 手机端点「解除锁定」→ 客户端恢复 ===')
mark2 = LOG.stat().st_size if LOG.exists() else 0
post('/unlock', {})
unlocked = False
for i in range(20):
    time.sleep(1)
    if '[lock] 已解除锁定' in log_from(mark2):
        unlocked = True
        print(f'  客户端在第 {i+1} 秒恢复')
        break
check('客户端解除锁定', unlocked, log_from(mark2)[-300:])

print('=== 8. 退出登录后必须重新登录 ===')
get('/logout')
html, _ = get('/')
check('登出后需登录', '家长登录' in html, html[:200])
html, code = post_raw('/login', {'pwd': 'wrongpass'})
check('错误密码被拒绝', code == 401 and '不正确' in html, code)
html, _ = post('/login', {'pwd': 'admin123'})
check('正确密码可登录', '今日剩余' in html, html[:150])

print('=== 9. 路径穿越 / 非法请求 ===')
try:
    html, code = get('/static/../../core/store.py')
    check('拒绝路径穿越', code in (404, 400) or 'sqlite3' not in html, code)
except urllib.error.HTTPError as e:
    check('拒绝路径穿越', True, e.code)

html, code = post_raw('/nonexistent', {})
check('未知 POST 返回 404', code == 404, code)

print()
print('=== 全部通过 ===' if ok else '=== 存在失败项 ===')
sys.exit(0 if ok else 1)
