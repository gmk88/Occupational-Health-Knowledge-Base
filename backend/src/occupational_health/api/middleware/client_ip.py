from __future__ import annotations

import ipaddress

from fastapi import Request


def _parse_ip(value: str | None):
    if not value:
        return None
    try:
        return ipaddress.ip_address(value.strip())
    except ValueError:
        return None


def _is_trusted_proxy(peer: str | None, trusted: set[str]) -> bool:
    address = _parse_ip(peer)
    if address is None:
        return False
    for entry in trusted:
        if entry == peer:
            return True
        try:
            if address in ipaddress.ip_network(entry, strict=False):
                return True
        except ValueError:
            continue
    return False


def resolve_client_ip(
    request: Request, trusted_proxies: set[str] | None = None
) -> str:
    """解析访客 IP，只信任受控代理写入的转发头。

    cloudflared 会把所有访客的连接源地址变成 127.0.0.1，真实 IP 只出现在
    ``CF-Connecting-IP``。仅当 TCP 对端是可信回环地址时才采信该头，避免
    外部伪造转发头绕过限流。
    """
    trusted = trusted_proxies or set()
    peer = request.client.host if request.client else None
    if _is_trusted_proxy(peer, trusted):
        cloudflare = _parse_ip(request.headers.get("cf-connecting-ip"))
        if cloudflare is not None:
            return str(cloudflare)
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            first = _parse_ip(forwarded.split(",")[0])
            if first is not None:
                return str(first)
    return peer or "anonymous"
