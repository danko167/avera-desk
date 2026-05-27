from __future__ import annotations

import os
import secrets
import sys
import threading
import time

from .paths import get_data_root, is_packaged_runtime
from .url_validation import normalize_http_or_https_url

LOCAL_AUTH_HEADER = "x-avera-local-token"

_DEFAULT_ALLOWED_ORIGINS = [
    "http://localhost:1420",
    "http://127.0.0.1:1420",
    "tauri://localhost",
    "http://tauri.localhost",
    "https://tauri.localhost",
]
_LOCAL_AUTH_TOKEN_PATH = get_data_root() / ".local-auth-token"
_PERSIST_LOCAL_AUTH_TOKEN_ENV = "AVERA_PERSIST_LOCAL_AUTH_TOKEN"
_WS_TICKET_TTL_SECONDS = 45
_ws_ticket_store: dict[str, float] = {}
_ws_ticket_lock = threading.Lock()


def _should_persist_local_auth_token() -> bool:
    configured = os.getenv(_PERSIST_LOCAL_AUTH_TOKEN_ENV)
    if configured is not None:
        return _truthy(configured)

    # Default: persist in dev to survive uvicorn reloads, avoid implicit
    # persistence in packaged runtime.
    return not is_packaged_runtime()


def _load_or_create_local_auth_token() -> str:
    if not _should_persist_local_auth_token():
        return secrets.token_urlsafe(32)

    try:
        token = _LOCAL_AUTH_TOKEN_PATH.read_text(encoding="utf-8").strip()
        if token:
            return token
    except OSError:
        pass

    token = secrets.token_urlsafe(32)
    try:
        _LOCAL_AUTH_TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        _LOCAL_AUTH_TOKEN_PATH.write_text(token, encoding="utf-8")
    except OSError:
        # If persistence fails, keep process-local token.
        pass
    return token


_local_auth_token = _load_or_create_local_auth_token()


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def get_local_auth_token() -> str:
    return _local_auth_token


def _prune_ws_tickets(now: float | None = None) -> None:
    current = now if now is not None else time.monotonic()
    expired = [ticket for ticket, expires_at in _ws_ticket_store.items() if expires_at <= current]
    for ticket in expired:
        _ws_ticket_store.pop(ticket, None)


def issue_local_ws_ticket() -> str:
    now = time.monotonic()
    with _ws_ticket_lock:
        _prune_ws_tickets(now)
        ticket = secrets.token_urlsafe(32)
        _ws_ticket_store[ticket] = now + _WS_TICKET_TTL_SECONDS
        return ticket


def consume_local_ws_ticket(ticket: str | None) -> bool:
    normalized = str(ticket or "").strip()
    if not normalized:
        return False

    now = time.monotonic()
    with _ws_ticket_lock:
        _prune_ws_tickets(now)
        expires_at = _ws_ticket_store.pop(normalized, None)
        if expires_at is None:
            return False
        return expires_at > now


def parse_allowed_origins() -> list[str]:
    configured = str(os.getenv("AVERA_ALLOWED_ORIGINS", "")).strip()
    if not configured:
        return list(_DEFAULT_ALLOWED_ORIGINS)
    values = [item.strip() for item in configured.split(",")]
    return [item.rstrip("/") for item in values if item]


def is_allowed_origin(origin: str | None, *, allowed_origins: list[str] | None = None) -> bool:
    normalized = str(origin or "").strip().rstrip("/")
    if not normalized:
        return False
    allowed = allowed_origins or parse_allowed_origins()
    return normalized in allowed


def should_enforce_loopback_host() -> bool:
    if _truthy(os.getenv("AVERA_ENFORCE_LOOPBACK")):
        return True

    profile = str(os.getenv("AVERA_DESK_PROFILE", "")).strip().lower()
    if profile in {"prod", "production", "release"}:
        return True

    return bool(getattr(sys, "frozen", False))


def should_enforce_local_auth() -> bool:
    if _truthy(os.getenv("AVERA_DISABLE_LOCAL_AUTH")):
        return False
    if os.getenv("PYTEST_CURRENT_TEST"):
        return False
    return True


def should_trust_forwarded_headers() -> bool:
    # Off by default: only enable when running behind an explicitly trusted proxy.
    return _truthy(os.getenv("AVERA_TRUST_PROXY_HEADERS"))


def normalize_base_url(value: str) -> str:
    return normalize_http_or_https_url(value)
