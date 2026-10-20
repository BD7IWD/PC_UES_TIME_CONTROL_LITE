# -*- coding: utf-8 -*-
"""SQLite 存储层（线程安全）。

用量同时写入注册表做冗余 —— 孩子删掉 data.db 也清不掉当天已用时间。

作者：野怼怼；https://www.bd7iwd.com
许可：MIT
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
import threading
import time
from datetime import date

from . import config

try:
    import winreg
except ImportError:
    winreg = None

REG_ROOT = r'Software\PCTimeControlLite'

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS settings (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        quota_minutes INTEGER NOT NULL DEFAULT 120,
        warn_minutes  TEXT    NOT NULL DEFAULT '10,5,1',
        admin_hash    TEXT    NOT NULL DEFAULT '',
        unlock_hash   TEXT    NOT NULL DEFAULT '',
        enabled       INTEGER NOT NULL DEFAULT 0,
        locked        INTEGER NOT NULL DEFAULT 0,
        lock_reason   TEXT,
        lock_style    TEXT    NOT NULL DEFAULT 'bsod',
        bsod_code     TEXT    NOT NULL DEFAULT 'CRITICAL_PROCESS_DIED',
        updated_at    TEXT    NOT NULL DEFAULT ''
    )""",
    """CREATE TABLE IF NOT EXISTS usage (
        stat_date    TEXT PRIMARY KEY,
        used_seconds INTEGER NOT NULL DEFAULT 0,
        unlock_count INTEGER NOT NULL DEFAULT 0,
        updated_at   TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS commands (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        type         TEXT NOT NULL,
        payload      TEXT,
        created_at   TEXT NOT NULL,
        delivered_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS events (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        type       TEXT NOT NULL,
        detail     TEXT,
        created_at TEXT NOT NULL
    )""",
]

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None


# ------------------------------------------------------------------ 密码

PBKDF2_ROUNDS = 120_000


def hash_pwd(pwd: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac('sha256', pwd.encode('utf-8'), salt, PBKDF2_ROUNDS)
    return salt.hex() + '$' + dk.hex()


def verify_pwd(pwd: str, stored: str) -> bool:
    try:
        salt_hex, dk_hex = str(stored).split('$', 1)
        dk = hashlib.pbkdf2_hmac('sha256', pwd.encode('utf-8'), bytes.fromhex(salt_hex), PBKDF2_ROUNDS)
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


# ------------------------------------------------------------------ 连接

def db() -> sqlite3.Connection:
    global _conn
    with _lock:
        if _conn is None:
            _conn = sqlite3.connect(str(config.DB_PATH), check_same_thread=False, timeout=10)
            _conn.row_factory = sqlite3.Row
            _conn.execute('PRAGMA journal_mode=WAL')
            for sql in SCHEMA:
                _conn.execute(sql)
            _conn.execute("INSERT OR IGNORE INTO settings (id, updated_at) VALUES (1, '')")
            _conn.commit()
        return _conn


def now() -> str:
    return time.strftime('%Y-%m-%d %H:%M:%S')


def today() -> str:
    return date.today().isoformat()


# ------------------------------------------------------- 注册表用量冗余

def _reg_write_usage(d: str, sec: int) -> None:
    if winreg is None:
        return
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, REG_ROOT, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, f'u_{d}', 0, winreg.REG_DWORD, int(sec) & 0xFFFFFFFF)
    except Exception:
        pass


def _reg_read_usage(d: str) -> int:
    if winreg is None:
        return 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_ROOT, 0, winreg.KEY_READ) as k:
            v, _ = winreg.QueryValueEx(k, f'u_{d}')
            return int(v)
    except Exception:
        return 0


# ------------------------------------------------------------------ 设置

def get_settings() -> dict:
    with _lock:
        row = db().execute('SELECT * FROM settings WHERE id = 1').fetchone()
    s = dict(row) if row else {}
    s.setdefault('quota_minutes', 120)
    s.setdefault('warn_minutes', '10,5,1')
    s.setdefault('admin_hash', '')
    s.setdefault('unlock_hash', '')
    s.setdefault('enabled', 1)
    s.setdefault('locked', 0)
    s.setdefault('lock_reason', None)
    s.setdefault('lock_style', 'bsod')
    s.setdefault('bsod_code', 'CRITICAL_PROCESS_DIED')
    s.setdefault('updated_at', '')
    return s


def is_initialized() -> bool:
    s = get_settings()
    return bool(s.get('admin_hash')) and bool(s.get('unlock_hash'))


def update_settings(**kw) -> None:
    if not kw:
        return
    allowed = {'quota_minutes', 'warn_minutes', 'admin_hash', 'unlock_hash',
               'enabled', 'locked', 'lock_reason', 'lock_style', 'bsod_code'}
    sets, vals = [], []
    for k, v in kw.items():
        if k in allowed:
            sets.append(f'{k} = ?')
            vals.append(v)
    if not sets:
        return
    sets.append('updated_at = ?')
    vals.append(now())
    with _lock:
        db().execute(f'UPDATE settings SET {", ".join(sets)} WHERE id = 1', vals)
        db().commit()


def warn_seconds(csv: str) -> list[int]:
    out = set()
    for p in str(csv or '').replace('，', ',').split(','):
        p = p.strip()
        if p.isdigit():
            m = int(p)
            if 1 <= m <= 720:
                out.add(m * 60)
    return sorted(out, reverse=True)


# ------------------------------------------------------------------ 用量

def get_used(d: str | None = None) -> int:
    d = d or today()
    with _lock:
        row = db().execute('SELECT used_seconds FROM usage WHERE stat_date = ?', (d,)).fetchone()
    v = int(row['used_seconds']) if row else 0
    return max(v, _reg_read_usage(d))


def set_used(sec: int, d: str | None = None) -> None:
    d = d or today()
    sec = max(0, int(sec))
    with _lock:
        db().execute(
            'INSERT INTO usage (stat_date, used_seconds, updated_at) VALUES (?,?,?) '
            'ON CONFLICT(stat_date) DO UPDATE SET used_seconds = excluded.used_seconds, updated_at = excluded.updated_at',
            (d, sec, now()))
        db().commit()
    _reg_write_usage(d, sec)


def add_used(delta: int, d: str | None = None) -> int:
    d = d or today()
    cur = get_used(d) + max(0, int(delta))
    set_used(cur, d)
    return cur


def reset_used(d: str | None = None) -> None:
    set_used(0, d)


def get_usage_row(d: str | None = None) -> dict:
    d = d or today()
    with _lock:
        row = db().execute('SELECT * FROM usage WHERE stat_date = ?', (d,)).fetchone()
    out = dict(row) if row else {'stat_date': d, 'used_seconds': 0, 'unlock_count': 0, 'updated_at': now()}
    out['used_seconds'] = max(int(out.get('used_seconds') or 0), _reg_read_usage(d))
    return out


def bump_unlock(d: str | None = None) -> None:
    d = d or today()
    with _lock:
        db().execute('INSERT INTO usage (stat_date, used_seconds, unlock_count, updated_at) '
                     'VALUES (?,?,1,?) ON CONFLICT(stat_date) DO UPDATE SET '
                     'unlock_count = unlock_count + 1, updated_at = excluded.updated_at',
                     (d, 0, now()))
        db().commit()


def recent_usage(days: int = 14) -> list[dict]:
    with _lock:
        rows = db().execute('SELECT * FROM usage ORDER BY stat_date DESC LIMIT ?', (days,)).fetchall()
    return [dict(r) for r in rows]


# ------------------------------------------------------------------ 指令

def push_command(ctype: str, payload: dict | None = None) -> None:
    with _lock:
        db().execute('INSERT INTO commands (type, payload, created_at) VALUES (?,?,?)',
                     (ctype, json.dumps(payload or {}, ensure_ascii=False), now()))
        db().commit()


def take_commands() -> list[dict]:
    with _lock:
        rows = db().execute('SELECT * FROM commands WHERE delivered_at IS NULL ORDER BY id ASC LIMIT 20').fetchall()
        if not rows:
            return []
        ids = [int(r['id']) for r in rows]
        db().execute(f'UPDATE commands SET delivered_at = ? WHERE id IN ({",".join("?" * len(ids))})',
                     [now()] + ids)
        db().commit()
    out = []
    for r in rows:
        try:
            pl = json.loads(r['payload'] or '{}')
        except Exception:
            pl = {}
        out.append({'id': int(r['id']), 'type': r['type'], 'payload': pl})
    return out


# ------------------------------------------------------------------ 事件

def add_event(etype: str, detail: str = '') -> None:
    with _lock:
        db().execute('INSERT INTO events (type, detail, created_at) VALUES (?,?,?)',
                     (etype, str(detail)[:255], now()))
        db().commit()


def recent_events(limit: int = 100) -> list[dict]:
    with _lock:
        rows = db().execute('SELECT * FROM events ORDER BY id DESC LIMIT ?', (limit,)).fetchall()
    return [dict(r) for r in rows]
