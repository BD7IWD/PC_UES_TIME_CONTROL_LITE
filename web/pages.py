# -*- coding: utf-8 -*-
"""手机端管理页面的 HTML 生成。

作者：野怼怼；https://www.bd7iwd.com
许可：MIT
"""
from __future__ import annotations

import html

from core import config


def h(s) -> str:
    return html.escape(str(s if s is not None else ''), quote=True)


def fmt_dur(sec: int) -> str:
    sec = max(0, int(sec))
    hh, mm, ss = sec // 3600, (sec % 3600) // 60, sec % 60
    if hh:
        return f'{hh}小时{mm}分'
    if mm:
        return f'{mm}分{ss}秒'
    return f'{ss}秒'


def clock(sec: int) -> str:
    sec = max(0, int(sec))
    return f'{sec // 3600:02d}:{(sec % 3600) // 60:02d}:{sec % 60:02d}'


def layout(title: str, body: str, active: str = '', logged: bool = False, flash: str = '') -> bytes:
    nav = ''
    if logged:
        items = [('home', '总览', '/'), ('settings', '设置', '/settings'), ('logs', '记录', '/logs')]
        links = ''.join(
            f'<a href="{u}" style="color:{"#fff" if k == active else "#a9b6c8"};'
            f'font-size:13.5px;margin-right:16px">{h(t)}</a>'
            for k, t, u in items
        )
        top_right = links + '<a href="/logout" style="font-size:13px;color:#8fa0b8">退出</a>'
    else:
        top_right = ''

    fl = f'<div class="flash ok">{h(flash)}</div>' if flash else ''

    doc = f'''<!DOCTYPE html>
<html lang="zh-CN"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<meta name="theme-color" content="#101827">
<title>{h(title)} - {h(config.APP_TITLE)}</title>
<link rel="stylesheet" href="/static/app.css">
</head><body>
<div class="top"><div class="wrap">
  <div class="brand">🖥️ {h(config.APP_TITLE)}<small>单机版 v{config.APP_VER}</small></div>
  <div class="sp"></div>{top_right}
</div></div>
<div class="wrap">{fl}{body}</div>
<div class="foot">作者：野怼怼；https://www.bd7iwd.com</div>
许可：MIT
</body></html>'''
    return doc.encode('utf-8')


# ---------------------------------------------------------------- 首次设置

def page_setup(err: str = '') -> bytes:
    e = f'<div class="flash err">{h(err)}</div>' if err else ''
    body = f'''
<div class="auth">
  <div class="card">
    <h1>👋 首次使用</h1>
    <p class="sub">设置两个密码，请记牢。设置完就能在手机上看孩子电脑的使用情况了。</p>
    {e}
    <form method="post" action="/setup">
      <label>管理密码（登录这个网页用，≥6 位）
        <input type="password" name="admin_pwd" required minlength="6" autocomplete="new-password">
      </label>
      <label>解锁密码（电脑蓝屏后解锁用，≥4 位）
        <input type="password" name="unlock_pwd" required minlength="4" autocomplete="new-password">
      </label>
      <label>每天允许使用多久（分钟）
        <input type="number" name="quota" value="120" min="1" max="1440" required>
      </label>
      <button class="btn primary" type="submit">完成设置</button>
    </form>
  </div>
</div>'''
    return layout('首次设置', body)


# ---------------------------------------------------------------- 登录

def page_login(err: str = '') -> bytes:
    e = f'<div class="flash err">{h(err)}</div>' if err else ''
    body = f'''
<div class="auth">
  <div class="card">
    <h1>🔑 家长登录</h1>
    <p class="sub">输入管理密码，查看和调整孩子电脑的使用时间。</p>
    {e}
    <form method="post" action="/login">
      <label>管理密码
        <input type="password" name="pwd" required autofocus autocomplete="current-password">
      </label>
      <button class="btn primary" type="submit">登录</button>
    </form>
  </div>
</div>'''
    return layout('登录', body)


# ---------------------------------------------------------------- 总览

def page_home(st: dict, flash: str = '') -> bytes:
    quota = st['quota']
    used = st['used']
    left = st['left']
    pct = st['pct']
    cls = 'hot' if pct >= 95 else ('warn' if pct >= 75 else '')

    if st['locked']:
        badge, state_txt = '<span class="badge err">已锁定</span>', '电脑正在显示蓝屏，需要密码解锁'
    elif not st['enabled']:
        badge, state_txt = '<span class="badge idle">待机中</span>', '没有在计时，家长自己在用电脑'
    elif left <= 0:
        badge, state_txt = '<span class="badge err">时间到</span>', '今日时间已用完'
    elif left <= 600:
        badge, state_txt = '<span class="badge warn">快用完了</span>', '剩余时间不多'
    else:
        badge, state_txt = '<span class="badge ok">计时中</span>', '正在倒计时'

    lock_btn = ('<form method="post" action="/unlock"><button class="btn" type="submit">🔓 解除锁定</button></form>'
                if st['locked'] else
                '<form method="post" action="/lock"><button class="btn danger" type="submit">🔒 立即锁定</button></form>')

    if st['enabled']:
        main_btn = '''<form method="post" action="/pause">
        <button class="btn big pause" type="submit">&#9208; 暂停管控</button>
      </form>
      <p class="hint" style="margin:10px 0 0">家长自己在用电脑时点这里：停止计时、不锁屏。</p>'''
    else:
        main_btn = f'''<form method="post" action="/start">
        <button class="btn big go" type="submit">&#9654; 开始管控（{fmt_dur(quota)}）</button>
      </form>
      <p class="hint" style="margin:10px 0 0">发现孩子在玩时点这里：从头开始计时，时间到自动蓝屏。</p>'''

    body = f'''
<div class="card">
  <div class="hero">
    <div class="ring {cls}" style="--p:{pct}">
      <div class="mid"><b>{clock(left)}</b><span>今日剩余</span></div>
    </div>
    <div class="hero-txt">
      <div class="state">{state_txt}</div>
      <div class="big">{fmt_dur(left)}</div>
      <div class="meta">{badge} 已用 {fmt_dur(used)} / 额度 {fmt_dur(quota)}</div>
    </div>
  </div>
</div>

<div class="card" style="text-align:center">
  {main_btn}
</div>

<div class="card">
  <h2>⚡ 快捷操作</h2>
  <div class="grid2" style="margin-bottom:10px">{lock_btn}
    <form method="post" action="/reset"><button class="btn ghost" type="submit">↺ 重置今日用时</button></form>
  </div>
  <form method="post" action="/toast">
    <label>给孩子发一句话
      <input type="text" name="text" placeholder="例如：该写作业了，20 分钟后爸爸来看" maxlength="120">
    </label>
    <button class="btn primary" type="submit">📢 发到电脑上</button>
  </form>
</div>

<div class="card">
  <h2>📋 今日情况</h2>
  <div class="kv"><span>每日额度</span><b>{fmt_dur(quota)}</b></div>
  <div class="kv"><span>今日已用</span><b>{fmt_dur(used)}</b></div>
  <div class="kv"><span>剩余可用</span><b>{fmt_dur(left)}</b></div>
  <div class="kv"><span>今日解锁次数</span><b>{st['unlock_count']} 次</b></div>
  <div class="kv"><span>锁定画面</span><b>{'模拟蓝屏' if st['lock_style'] == 'bsod' else '电脑损坏弹窗'}</b></div>
</div>

<div class="card">
  <h2>📱 手机访问地址</h2>
  <p class="muted" style="margin:0 0 8px">家里其他设备连同一个 Wi-Fi，就能用这些地址打开本页面：</p>
  {''.join(f'<div class="kv"><span>地址</span><b class="mono">{h(u)}</b></div>' for u in st['urls'])}
  <p class="hint" style="margin:10px 0 0">电脑 IP 变了就打不开了，可在电脑右下角托盘图标右键查看当前地址。</p>
</div>'''
    return layout('总览', body, 'home', True, flash)


# ---------------------------------------------------------------- 设置

def page_settings(st: dict, flash: str = '', err: str = '') -> bytes:
    e = f'<div class="flash err">{h(err)}</div>' if err else ''
    s = st['settings']
    bsod_sel = 'selected' if s.get('lock_style') == 'bsod' else ''
    popup_sel = 'selected' if s.get('lock_style') == 'popup' else ''
    body = f'''
{e}
<div class="card">
  <h2>⏱️ 时间设置</h2>
  <form method="post" action="/settings">
    <label>每天允许使用多久（分钟）
      <input type="number" name="quota" value="{int(s['quota_minutes'])}" min="1" max="1440" required>
    </label>
    <p class="hint" style="margin:-4px 0 16px">时间用完会<b>直接进入锁定画面</b>，不做任何提前提醒。</p>
    <label>锁定画面样式
      <select name="style" style="display:block;width:100%;margin-top:6px;padding:12px 13px;font-size:16px;
        border:1px solid var(--line);border-radius:11px;background:#fff;font-family:inherit">
        <option value="bsod" {bsod_sel}>模拟 Windows 蓝屏（默认，更像电脑坏了）</option>
        <option value="popup" {popup_sel}>弹出「电脑已损坏」错误框</option>
      </select>
    </label>
    <button class="btn primary" type="submit" style="margin-top:6px">保存设置</button>
  </form>
</div>

<div class="card">
  <h2>🔑 修改密码</h2>
  <form method="post" action="/password">
    <label>新的解锁密码（蓝屏解锁用，留空不改）
      <input type="password" name="unlock_pwd" autocomplete="new-password" minlength="4">
    </label>
    <label>新的管理密码（登录本页用，留空不改）
      <input type="password" name="admin_pwd" autocomplete="new-password" minlength="6">
    </label>
    <button class="btn" type="submit">更新密码</button>
  </form>
</div>

<div class="card">
  <h2>⚠️ 危险操作</h2>
  <p class="hint" style="margin-top:-4px">重置后今天从头开始计时（相当于再给一次完整时长）。</p>
  <form method="post" action="/reset"><button class="btn ghost" type="submit">重置今日已用时间</button></form>
</div>'''
    return layout('设置', body, 'settings', True, flash)


# ---------------------------------------------------------------- 记录

def page_logs(usage: list[dict], events: list[dict], quota: int) -> bytes:
    tmap = {
        'warning_shown': ('提醒已弹出', 'warn'),
        'locked': ('已锁定', 'err'),
        'unlocked': ('密码解锁', 'ok'),
        'unlock_failed': ('密码错误', 'err'),
        'started': ('程序启动', 'idle'),
        'stopped': ('程序退出', 'idle'),
        'parent_lock': ('手机远程锁定', 'err'),
        'parent_unlock': ('手机解除锁定', 'ok'),
        'parent_reset': ('手机重置用时', 'ok'),
        'parent_toast': ('手机发提醒', 'idle'),
        'setup': ('完成初始化', 'ok'),
    }
    urows = ''.join(
        f'<tr><td class="mono">{h(u["stat_date"])}</td><td><b>{fmt_dur(u["used_seconds"])}</b></td>'
        f'<td class="muted">{fmt_dur(quota)}</td><td>{u["unlock_count"]}</td></tr>'
        for u in usage
    ) or '<tr><td colspan="4" class="muted">暂无数据</td></tr>'

    erows = ''.join(
        f'<tr><td class="mono" style="white-space:nowrap">{h(e["created_at"][5:16])}</td>'
        f'<td><span class="badge {tmap.get(e["type"], ("", "idle"))[1]}">'
        f'{h(tmap.get(e["type"], (e["type"], ""))[0])}</span></td>'
        f'<td class="muted">{h(e["detail"] or "—")}</td></tr>'
        for e in events
    ) or '<tr><td colspan="3" class="muted">暂无记录</td></tr>'

    body = f'''
<div class="card">
  <h2>📊 最近用量</h2>
  <table>
    <thead><tr><th>日期</th><th>已用</th><th>额度</th><th>解锁</th></tr></thead>
    <tbody>{urows}</tbody>
  </table>
</div>
<div class="card">
  <h2>📝 事件记录</h2>
  <table>
    <thead><tr><th>时间</th><th>事件</th><th>说明</th></tr></thead>
    <tbody>{erows}</tbody>
  </table>
</div>'''
    return layout('记录', body, 'logs', True)


# ---------------------------------------------------------------- 通用提示页

def page_msg(title: str, icon: str, text: str, back: str = '/') -> bytes:
    body = f'''
<div class="auth">
  <div class="card" style="text-align:center">
    <div style="font-size:46px;line-height:1.2">{icon}</div>
    <h1 style="text-align:center">{h(title)}</h1>
    <p class="sub" style="text-align:center">{h(text)}</p>
    <a class="btn primary" href="{h(back)}" style="text-decoration:none">返回</a>
  </div>
</div>'''
    return layout(title, body)
