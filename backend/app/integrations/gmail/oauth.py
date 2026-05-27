"""OAuth 2.0 PKCE flow for Gmail access."""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import secrets
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import urlencode, urlparse

import httpx

from ...core.secret_store import clear_secret, get_secret, get_secret_persistence, has_secret, set_secret

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/userinfo.email",
]
_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
_REFRESH_TOKEN_SECRET = "gmail_refresh_token"
_CLIENT_SECRET_NAME = "gmail_client_secret"
_PENDING_AUTH_FLOW_TTL_SECONDS = 10 * 60
_MAX_PENDING_AUTH_FLOWS = 256
logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _PendingAuthFlow:
    code_verifier: str
    redirect_uri: str


_pending_auth_flows: dict[str, tuple[_PendingAuthFlow, float]] = {}


def _prune_pending_auth_flows() -> None:
    now = time.monotonic()

    expired = [
        state
        for state, (_, created_at) in _pending_auth_flows.items()
        if now - created_at > _PENDING_AUTH_FLOW_TTL_SECONDS
    ]
    for state in expired:
        _pending_auth_flows.pop(state, None)

    overflow = len(_pending_auth_flows) - _MAX_PENDING_AUTH_FLOWS
    if overflow <= 0:
        return

    for state, _ in sorted(_pending_auth_flows.items(), key=lambda item: item[1][1])[:overflow]:
        _pending_auth_flows.pop(state, None)


class OAuthSetupRequiredError(RuntimeError):
    """Raised when required OAuth settings are missing or invalid."""

    def __init__(self, missing_settings: list[str]):
        self.missing_settings = missing_settings
        super().__init__(
            "OAuth setup required: " + ", ".join(missing_settings)
            if missing_settings
            else "OAuth setup required"
        )


def _urlsafe_b64_no_padding(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _is_valid_redirect_uri(value: str) -> bool:
    try:
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except ValueError:
        return False


async def _get_config(db: "AsyncSession | None" = None) -> dict:
    if db:
        from ...services.shared.preferences import get_settings

        settings = await get_settings(db)
        return {
            "client_id": str(settings.get("gmail_client_id", "")).strip(),
            "client_secret": str(get_secret(_CLIENT_SECRET_NAME) or os.getenv("GMAIL_CLIENT_SECRET", "")).strip(),
            "redirect_uri": str(
                settings.get("gmail_redirect_url", "http://localhost:8000/api/oauth/google/callback")
            ).strip(),
        }

    return {
        "client_id": str(os.getenv("GMAIL_CLIENT_ID", "")).strip(),
        "client_secret": str(get_secret(_CLIENT_SECRET_NAME) or os.getenv("GMAIL_CLIENT_SECRET", "")).strip(),
        "redirect_uri": str(
            os.getenv("GMAIL_REDIRECT_URL", "http://localhost:8000/api/oauth/google/callback")
        ).strip(),
    }


async def get_missing_required_settings(db: "AsyncSession | None" = None) -> list[str]:
    config = await _get_config(db)
    missing: list[str] = []

    if not config.get("client_id"):
        missing.append("gmail_client_id")
    if not config.get("client_secret"):
        missing.append("gmail_client_secret")

    redirect_uri = str(config.get("redirect_uri", "")).strip()
    if not _is_valid_redirect_uri(redirect_uri):
        missing.append("gmail_redirect_url")

    return missing


async def get_auth_url(db: "AsyncSession | None" = None) -> str:
    missing = await get_missing_required_settings(db)
    if missing:
        raise OAuthSetupRequiredError(missing)

    config = await _get_config(db)
    state = secrets.token_urlsafe(20)
    code_verifier = _urlsafe_b64_no_padding(secrets.token_bytes(48))
    challenge = _urlsafe_b64_no_padding(hashlib.sha256(code_verifier.encode("ascii")).digest())

    _prune_pending_auth_flows()
    _pending_auth_flows[state] = (
        _PendingAuthFlow(
            code_verifier=code_verifier,
            redirect_uri=config["redirect_uri"],
        ),
        time.monotonic(),
    )

    params = {
        "client_id": config["client_id"],
        "redirect_uri": config["redirect_uri"],
        "response_type": "code",
        "scope": " ".join(_SCOPES),
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }

    return f"{_AUTH_URL}?{urlencode(params)}"


async def exchange_auth_response(
    auth_response: dict[str, str],
    db: "AsyncSession | None" = None,
) -> dict | None:
    state = auth_response.get("state", "")
    code = auth_response.get("code", "")
    if not state or not code:
        return None

    _prune_pending_auth_flows()
    pending_entry = _pending_auth_flows.pop(state, None)
    flow = pending_entry[0] if pending_entry is not None else None
    if flow is None:
        return None

    config = await _get_config(db)
    data = {
        "client_id": config["client_id"],
        "client_secret": config["client_secret"],
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": flow.redirect_uri,
        "code_verifier": flow.code_verifier,
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(_TOKEN_URL, data=data, timeout=30)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        logger.warning("gmail_oauth_token_exchange_failed error=%s", exc)
        return None

    refresh_token = str(payload.get("refresh_token") or "").strip()
    if refresh_token:
        set_secret(_REFRESH_TOKEN_SECRET, refresh_token)

    access_token = str(payload.get("access_token") or "").strip()
    if not access_token:
        return None

    return {
        "access_token": access_token,
        "expires_in": payload.get("expires_in"),
    }


async def get_access_token(db: "AsyncSession | None" = None) -> str | None:
    missing = await get_missing_required_settings(db)
    if missing:
        return None

    refresh_token = get_secret(_REFRESH_TOKEN_SECRET)
    if not refresh_token:
        return None

    config = await _get_config(db)
    data = {
        "client_id": config["client_id"],
        "client_secret": config["client_secret"],
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(_TOKEN_URL, data=data, timeout=30)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status in {400, 401}:
            clear_secret(_REFRESH_TOKEN_SECRET)
        logger.warning("gmail_oauth_refresh_http_status_failed status=%s error=%s", status, exc)
        return None
    except httpx.HTTPError as exc:
        logger.warning("gmail_oauth_refresh_failed error=%s", exc)
        return None

    return str(payload.get("access_token") or "").strip() or None


def is_authenticated() -> bool:
    return has_secret(_REFRESH_TOKEN_SECRET)


def logout() -> None:
    clear_secret(_REFRESH_TOKEN_SECRET)


def get_token_persistence() -> str:
    return get_secret_persistence(_REFRESH_TOKEN_SECRET)


async def get_authenticated_mailbox(db: "AsyncSession | None" = None) -> str | None:
    access_token = await get_access_token(db)
    if not access_token:
        return None

    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(_USERINFO_URL, headers=headers, timeout=20)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        logger.warning("gmail_oauth_mailbox_lookup_failed error=%s", exc)
        return None

    email = str(payload.get("email") or "").strip()
    return email or None
