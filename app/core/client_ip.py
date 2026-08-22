"""
Helpers to resolve client IP behind reverse proxies (Nginx/Cloudflare).
"""
from __future__ import annotations

from ipaddress import ip_address
from typing import Optional

from fastapi import Request


def _normalize_ip(value: str) -> Optional[str]:
    """Return a normalized IP string or None if invalid."""
    if not value:
        return None

    candidate = value.strip()
    if not candidate:
        return None

    # Handle bracketed IPv6: [2001:db8::1]:443
    if candidate.startswith("[") and "]" in candidate:
        candidate = candidate[1:candidate.index("]")]

    # Handle IPv4 with port: 203.0.113.10:54321
    if "." in candidate and ":" in candidate:
        host, _, _port = candidate.rpartition(":")
        if host:
            candidate = host

    try:
        return str(ip_address(candidate))
    except ValueError:
        return None


def get_client_ip(request: Request) -> str:
    """
    Resolve real client IP with trusted header order:
    CF-Connecting-IP -> X-Forwarded-For (first hop) -> X-Real-IP -> socket peer.
    """
    cf_ip = _normalize_ip(request.headers.get("CF-Connecting-IP", ""))
    if cf_ip:
        return cf_ip

    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        first_hop = forwarded_for.split(",")[0].strip()
        xff_ip = _normalize_ip(first_hop)
        if xff_ip:
            return xff_ip

    real_ip = _normalize_ip(request.headers.get("X-Real-IP", ""))
    if real_ip:
        return real_ip

    peer_ip = request.client.host if request.client else ""
    socket_ip = _normalize_ip(peer_ip)
    return socket_ip or "unknown"
