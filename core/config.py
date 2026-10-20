# -*- coding: utf-8 -*-
"""配置与路径。单机版：数据放在 %LOCALAPPDATA%，孩子不容易翻到。

作者：野怼怼；https://www.bd7iwd.com
许可：MIT
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

APP_NAME = 'PCTimeControlLite'
APP_TITLE = '儿童电脑使用时长控制'
APP_VER = '2.1.0'
DEFAULT_PORT = 8080

#: Chromium / Chrome / Edge / 手机浏览器共有的「不安全端口」黑名单。
#: 浏览器遇到这些端口会直接报 ERR_UNSAFE_PORT，连请求都不发出去 ——
#: 服务端明明在监听、本机 curl 也通，但浏览器就是打不开。
#: 6666 就在里面（IRC 端口段 6665-6669），所以不能用作 Web 端口。
UNSAFE_PORTS = frozenset({
    1, 7, 9, 11, 13, 15, 17, 19, 20, 21, 22, 23, 25, 37, 42, 43, 53, 69, 77, 79,
    87, 95, 101, 102, 103, 104, 109, 110, 111, 113, 115, 117, 119, 123, 135, 137,
    139, 143, 161, 179, 389, 427, 465, 512, 513, 514, 515, 526, 530, 531, 532,
    540, 548, 554, 556, 563, 587, 601, 636, 989, 990, 993, 995, 1719, 1720, 1723,
    2049, 3659, 4045, 5060, 5061, 6000, 6566, 6665, 6666, 6667, 6668, 6669, 6697,
    10080,
})

#: 优先尝试的端口（都在浏览器安全范围内）
PORT_CANDIDATES = (8080, 8081, 8082, 8088, 8888, 9000, 9080, 18080)

DEFAULT_CFG = {
    'port': DEFAULT_PORT,
    'bind': '0.0.0.0',
    'watchdog': 1,
    'hide_console': 1,
}


def is_unsafe_port(p) -> bool:
    try:
        return int(p) in UNSAFE_PORTS
    except Exception:
        return True


def port_free(port: int) -> bool:
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('0.0.0.0', int(port)))
        return True
    except OSError:
        return False
    finally:
        try:
            s.close()
        except Exception:
            pass


def pick_port(preferred=None) -> int:
    """挑一个「浏览器能用 + 没被占用」的端口。"""
    order: list[int] = []
    if preferred is not None and not is_unsafe_port(preferred):
        order.append(int(preferred))
    for p in PORT_CANDIDATES:
        if p not in order:
            order.append(p)
    for p in order:
        if is_unsafe_port(p):
            continue
        if port_free(p):
            return p
    # 兜底：让系统分配一个空闲端口
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(('0.0.0.0', 0))
        return int(s.getsockname()[1])
    finally:
        try:
            s.close()
        except Exception:
            pass


def app_dir() -> Path:
    """程序所在目录（exe 或 main.py 所在处）。"""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    base = os.environ.get('LOCALAPPDATA') or str(Path.home())
    d = Path(base) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


DATA_DIR = data_dir()
DB_PATH = DATA_DIR / 'data.db'
CFG_PATH = DATA_DIR / 'config.json'
LOG_PATH = DATA_DIR / 'client.log'
WD_PID = DATA_DIR / 'watchdog.pid'


def load_cfg() -> dict:
    cfg = dict(DEFAULT_CFG)
    try:
        if CFG_PATH.exists():
            d = json.loads(CFG_PATH.read_text(encoding='utf-8'))
            if isinstance(d, dict):
                cfg.update({k: d[k] for k in DEFAULT_CFG if k in d})
    except Exception as e:
        log(f'读取 config.json 失败: {e}')
    return cfg


def save_cfg(cfg: dict) -> None:
    try:
        CFG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding='utf-8')
    except Exception as e:
        log(f'写入 config.json 失败: {e}')


def log(msg: str) -> None:
    line = time.strftime('%Y-%m-%d %H:%M:%S ') + str(msg)
    try:
        if LOG_PATH.exists() and LOG_PATH.stat().st_size > 1024 * 1024:
            LOG_PATH.write_text('', encoding='utf-8')
        with open(LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass
