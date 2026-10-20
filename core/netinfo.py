# -*- coding: utf-8 -*-
"""获取本机局域网 IP，拼出手机可访问的地址。

作者：野怼怼；https://www.bd7iwd.com
许可：MIT
"""
from __future__ import annotations

import socket


def primary_ip() -> str:
    """本机对外网卡 IP（不发包，只让系统选路由）。"""
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.3)
        s.connect(('8.8.8.8', 80))
        return s.getsockname()[0]
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return '127.0.0.1'
    finally:
        if s is not None:
            try:
                s.close()
            except Exception:
                pass


def access_urls(port: int) -> list[str]:
    """返回 [http://IP:端口, http://主机名:端口]，去重且本机 IP 排第一。"""
    out: list[str] = []
    ip = primary_ip()
    if ip and not ip.startswith('127.'):
        out.append(f'http://{ip}:{port}')
    try:
        hn = socket.gethostname()
        if hn:
            out.append(f'http://{hn}:{port}')
    except Exception:
        pass
    out.append(f'http://127.0.0.1:{port}（仅本机）')
    return out
