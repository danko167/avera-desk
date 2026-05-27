from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse, urlunparse


def _resolve_host_to_ip(hostname: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        addr_info = socket.getaddrinfo(hostname, None)
    except OSError:
        return None

    for entry in addr_info:
        sockaddr = entry[4]
        if not sockaddr:
            continue
        try:
            return ipaddress.ip_address(sockaddr[0])
        except ValueError:
            continue
    return None


def is_loopback_host(host: str | None, *, resolve_dns: bool = True) -> bool:
    normalized = str(host or "").strip().lower().strip("[]")
    if not normalized:
        return False
    if normalized == "localhost":
        return True

    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        if not resolve_dns:
            return False

    resolved = _resolve_host_to_ip(normalized)
    return bool(resolved and resolved.is_loopback)


def is_private_or_loopback_host(host: str | None, *, resolve_dns: bool = True) -> bool:
    normalized = str(host or "").strip().lower().strip("[]")
    if not normalized:
        return False
    if normalized == "localhost":
        return True

    try:
        addr = ipaddress.ip_address(normalized)
    except ValueError:
        if not resolve_dns:
            return False
    else:
        return addr.is_loopback or addr.is_private

    resolved = _resolve_host_to_ip(normalized)
    return bool(resolved and (resolved.is_loopback or resolved.is_private))


def normalize_http_or_https_url(value: object, *, preserve_path: bool = False) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError("base_url is required")

    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("base_url must be a valid http:// or https:// URL")

    path = (parsed.path or "").rstrip("/") if preserve_path else ""
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", "")).rstrip("/")


def normalize_websocket_url(value: object, *, fallback_http_base_url: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return _derive_ws_url_from_http_base_url(fallback_http_base_url)

    try:
        parsed = urlparse(normalized)
        if not parsed.netloc:
            return _derive_ws_url_from_http_base_url(fallback_http_base_url)

        scheme = parsed.scheme
        if scheme in {"http", "https"}:
            scheme = "wss" if scheme == "https" else "ws"
        if scheme not in {"ws", "wss"}:
            return _derive_ws_url_from_http_base_url(fallback_http_base_url)

        path = parsed.path or ""
        if path in {"", "/"}:
            path = "/ws"

        return urlunparse((scheme, parsed.netloc, path, "", "", ""))
    except ValueError:
        return _derive_ws_url_from_http_base_url(fallback_http_base_url)


def _derive_ws_url_from_http_base_url(http_base_url: str) -> str:
    try:
        parsed = urlparse(http_base_url)
        ws_scheme = "wss" if parsed.scheme == "https" else "ws"
        return urlunparse((ws_scheme, parsed.netloc, "/ws", "", "", ""))
    except ValueError:
        return "ws://127.0.0.1:8000/ws"
