from __future__ import annotations

import asyncio
import logging
import os
from urllib.parse import urlparse, urlunparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.url_validation import is_loopback_host, normalize_http_or_https_url, normalize_websocket_url
from ...core.secret_store import clear_secret, get_secret, set_secret
from ...db.tables import Setting

_SETTINGS_KEY = "ui_preferences"
_SETTINGS_QUERY_TIMEOUT_SECONDS = 2.0
_DEFAULT_REDIRECT_URL = "http://localhost:8000/api/oauth/callback"
_DEFAULT_GMAIL_REDIRECT_URL = "http://localhost:8000/api/oauth/google/callback"
_DEFAULT_SPEECH_BASE_URL = "https://api.openai.com/v1"
_DEFAULT_SPEECH_MODEL = "whisper-1"
_DEFAULT_LLM_BASE_URL = "https://api.openai.com/v1"
_DEFAULT_APP_API_BASE_URL = "http://127.0.0.1:8000"
_DEFAULT_APP_WS_URL = "ws://127.0.0.1:8000/ws"
_DEFAULT_EMAIL_SYNC_INTERVAL_MINUTES = 5
_DEFAULT_SETTINGS = {
    "enable_transcription_trace": False,
    "enable_text_input_mode": False,
    "email_sync_interval_minutes": _DEFAULT_EMAIL_SYNC_INTERVAL_MINUTES,
    "app_api_base_url": _DEFAULT_APP_API_BASE_URL,
    "app_ws_url": _DEFAULT_APP_WS_URL,
    "email_provider": "m365",
    "m365_client_id": "",
    "m365_tenant_id": "",
    "m365_redirect_url": _DEFAULT_REDIRECT_URL,
    "gmail_client_id": "",
    "gmail_redirect_url": _DEFAULT_GMAIL_REDIRECT_URL,
    "speech_provider": str(os.getenv("STT_PROVIDER", os.getenv("LLM_PROVIDER", "openai"))).strip().lower() or "openai",
    "speech_model": str(os.getenv("STT_MODEL", _DEFAULT_SPEECH_MODEL)).strip() or _DEFAULT_SPEECH_MODEL,
    "speech_base_url": str(
        os.getenv("OPENAI_BASE_URL")
        or os.getenv("OPENROUTER_BASE_URL")
        or os.getenv("LOCAL_AI_BASE_URL")
        or _DEFAULT_SPEECH_BASE_URL
    ).strip() or _DEFAULT_SPEECH_BASE_URL,
    "llm_provider": str(os.getenv("LLM_PROVIDER", "openai")).strip().lower() or "openai",
    "llm_model": str(os.getenv("LLM_MODEL", os.getenv("STT_MODEL", ""))).strip(),
    "llm_base_url": str(
        os.getenv("OPENAI_BASE_URL")
        or os.getenv("OPENROUTER_BASE_URL")
        or _DEFAULT_LLM_BASE_URL
    ).strip() or _DEFAULT_LLM_BASE_URL,
}

_cached_normalized_settings: dict | None = None
logger = logging.getLogger(__name__)

_GMAIL_CLIENT_SECRET_NAME = "gmail_client_secret"
_TRANSIENT_SETTINGS_FLAGS = {
    "gmail_client_secret_configured",
    "speech_api_key_configured",
    "llm_api_key_configured",
}


def _default_base_url(provider: str) -> str:
    if provider == "openrouter":
        return str(os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")).strip() or "https://openrouter.ai/api/v1"
    if provider == "local":
        return str(os.getenv("LOCAL_AI_BASE_URL", "http://localhost:11434/v1")).strip() or "http://localhost:11434/v1"
    return str(os.getenv("OPENAI_BASE_URL", _DEFAULT_SPEECH_BASE_URL)).strip() or _DEFAULT_SPEECH_BASE_URL


def _default_api_key(provider: str) -> str:
    if provider == "openrouter":
        return str(os.getenv("OPENROUTER_API_KEY", "")).strip()
    if provider == "local":
        return str(os.getenv("LOCAL_AI_API_KEY", "")).strip()
    return str(os.getenv("OPENAI_API_KEY", "")).strip()


def _has_gmail_client_secret() -> bool:
    return bool(get_secret(_GMAIL_CLIENT_SECRET_NAME) or str(os.getenv("GMAIL_CLIENT_SECRET", "")).strip())


def _has_ai_api_key(secret_name: str, provider: str) -> bool:
    return bool(get_secret(secret_name) or _default_api_key(provider))


def _strip_transient_settings_flags(raw: dict | None) -> dict | None:
    if not isinstance(raw, dict):
        return raw

    for key in _TRANSIENT_SETTINGS_FLAGS:
        raw.pop(key, None)
    return raw


def _migrate_legacy_gmail_client_secret(raw: dict | None) -> tuple[dict, bool]:
    if not isinstance(raw, dict):
        return {}, False

    migrated = dict(raw)
    legacy_secret = str(migrated.pop("gmail_client_secret", "")).strip()
    if legacy_secret and not get_secret(_GMAIL_CLIENT_SECRET_NAME):
        set_secret(_GMAIL_CLIENT_SECRET_NAME, legacy_secret)

    return migrated, legacy_secret != ""


def _normalize_sync_interval_minutes(value: object) -> int:
    try:
        minutes = int(value)
    except (TypeError, ValueError):
        return _DEFAULT_EMAIL_SYNC_INTERVAL_MINUTES

    if minutes < 1:
        return 1
    if minutes > 60:
        return 60
    return minutes


def _canonicalize_api_base_url(value: object) -> str:
    try:
        return normalize_http_or_https_url(value)
    except ValueError:
        return _DEFAULT_APP_API_BASE_URL


def _validate_configured_api_base_url(value: object) -> str:
    try:
        normalized = normalize_http_or_https_url(value)
    except ValueError as exc:
        raise ValueError("API Base URL must be a valid http:// or https:// URL.") from exc

    parsed = urlparse(normalized)
    if parsed.scheme == "http" and not is_loopback_host(parsed.hostname):
        raise ValueError("Non-local API Base URL values must use https://.")

    return normalized


def _derive_ws_url_from_api_base_url(api_base_url: str) -> str:
    return normalize_websocket_url("", fallback_http_base_url=api_base_url)


def _canonicalize_ws_url(value: object, *, api_base_url: str) -> str:
    return normalize_websocket_url(value, fallback_http_base_url=api_base_url)


def _validate_configured_ws_url(value: object, *, api_base_url: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return _derive_ws_url_from_api_base_url(api_base_url)

    try:
        parsed = urlparse(normalized)
    except ValueError as exc:
        raise ValueError("WebSocket URL must be a valid ws:// or wss:// URL.") from exc

    if not parsed.netloc:
        raise ValueError("WebSocket URL must be a valid ws:// or wss:// URL.")

    scheme = parsed.scheme
    if scheme in {"http", "https"}:
        if scheme == "http" and not is_loopback_host(parsed.hostname):
            raise ValueError("Non-local WebSocket URL values must use wss://.")
        scheme = "wss" if scheme == "https" else "ws"
    if scheme not in {"ws", "wss"}:
        raise ValueError("WebSocket URL must be a valid ws:// or wss:// URL.")
    if scheme == "ws" and not is_loopback_host(parsed.hostname):
        raise ValueError("Non-local WebSocket URL values must use wss://.")

    path = parsed.path or ""
    if path in {"", "/"}:
        path = "/ws"

    return urlunparse((scheme, parsed.netloc, path, "", "", ""))


def _normalize_settings(raw: dict | None) -> dict:
    if not isinstance(raw, dict):
        return dict(_DEFAULT_SETTINGS)

    raw = _strip_transient_settings_flags(raw)
    migrated_raw, had_legacy_gmail_secret = _migrate_legacy_gmail_client_secret(raw)

    redirect = str(migrated_raw.get("m365_redirect_url", _DEFAULT_REDIRECT_URL)).strip()
    if not redirect:
        redirect = _DEFAULT_REDIRECT_URL

    gmail_redirect = str(migrated_raw.get("gmail_redirect_url", _DEFAULT_GMAIL_REDIRECT_URL)).strip()
    if not gmail_redirect:
        gmail_redirect = _DEFAULT_GMAIL_REDIRECT_URL

    email_provider = str(migrated_raw.get("email_provider", "m365")).strip().lower() or "m365"
    if email_provider not in {"m365", "gmail"}:
        email_provider = "m365"

    speech_provider = str(migrated_raw.get("speech_provider", _DEFAULT_SETTINGS["speech_provider"])).strip().lower() or "openai"
    if speech_provider not in {"openai", "openrouter", "local"}:
        speech_provider = "openai"

    llm_provider = str(migrated_raw.get("llm_provider", _DEFAULT_SETTINGS["llm_provider"])).strip().lower() or "openai"
    if llm_provider not in {"openai", "openrouter", "local"}:
        llm_provider = "openai"

    speech_base_url = str(migrated_raw.get("speech_base_url", _default_base_url(speech_provider))).strip() or _default_base_url(speech_provider)
    llm_base_url = str(migrated_raw.get("llm_base_url", _default_base_url(llm_provider))).strip() or _default_base_url(llm_provider)

    app_api_base_url = _canonicalize_api_base_url(migrated_raw.get("app_api_base_url", _DEFAULT_APP_API_BASE_URL))
    app_ws_url = _canonicalize_ws_url(migrated_raw.get("app_ws_url", _DEFAULT_APP_WS_URL), api_base_url=app_api_base_url)
    sync_interval_minutes = _normalize_sync_interval_minutes(
        migrated_raw.get("email_sync_interval_minutes", _DEFAULT_EMAIL_SYNC_INTERVAL_MINUTES)
    )

    return {
        "enable_transcription_trace": bool(migrated_raw.get("enable_transcription_trace", False)),
        "enable_text_input_mode": bool(migrated_raw.get("enable_text_input_mode", False)),
        "email_sync_interval_minutes": sync_interval_minutes,
        "app_api_base_url": app_api_base_url,
        "app_ws_url": app_ws_url,
        "email_provider": email_provider,
        "m365_client_id": str(migrated_raw.get("m365_client_id", "")),
        "m365_tenant_id": str(migrated_raw.get("m365_tenant_id", "")),
        "m365_redirect_url": redirect,
        "gmail_client_id": str(migrated_raw.get("gmail_client_id", "")),
        "gmail_redirect_url": gmail_redirect,
        "speech_provider": speech_provider,
        "speech_model": str(migrated_raw.get("speech_model", _DEFAULT_SETTINGS["speech_model"])).strip()
        or _DEFAULT_SETTINGS["speech_model"],
        "speech_base_url": speech_base_url,
        "llm_provider": llm_provider,
        "llm_model": str(migrated_raw.get("llm_model", _DEFAULT_SETTINGS["llm_model"])).strip(),
        "llm_base_url": llm_base_url,
    }


def _decorate_settings(raw: dict, *, gmail_client_secret_configured: bool | None = None) -> dict:
    speech_provider = raw.get("speech_provider", "openai")
    llm_provider = raw.get("llm_provider", "openai")
    gmail_secret_flag = _has_gmail_client_secret() if gmail_client_secret_configured is None else gmail_client_secret_configured
    speech_api_key_configured = _has_ai_api_key("speech_api_key", speech_provider)
    llm_api_key_configured = _has_ai_api_key("llm_api_key", llm_provider)

    return {
        **raw,
        "gmail_client_secret_configured": gmail_secret_flag,
        "speech_api_key_configured": speech_api_key_configured,
        "llm_api_key_configured": llm_api_key_configured,
    }


async def get_settings(db: AsyncSession) -> dict:
    global _cached_normalized_settings

    try:
        result = await asyncio.wait_for(
            db.execute(select(Setting).where(Setting.key == _SETTINGS_KEY)),
            timeout=_SETTINGS_QUERY_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning("settings_query_timed_out_using_cache")
        fallback = _cached_normalized_settings or dict(_DEFAULT_SETTINGS)
        return _decorate_settings(dict(fallback))
    record = result.scalar_one_or_none()

    if record is None:
        # Keep read path lock-free: callers should still receive defaults even if
        # another task currently holds the SQLite write lock.
        fallback = _cached_normalized_settings or dict(_DEFAULT_SETTINGS)
        return _decorate_settings(dict(fallback))

    raw_value = record.value if isinstance(record.value, dict) else {}
    had_legacy_gmail_secret = bool(str(raw_value.get("gmail_client_secret", "")).strip())
    normalized = _normalize_settings(raw_value)
    _cached_normalized_settings = dict(normalized)
    return _decorate_settings(
        dict(normalized),
        gmail_client_secret_configured=had_legacy_gmail_secret or _has_gmail_client_secret(),
    )


async def clear_ai_secrets(db: AsyncSession) -> dict:
    global _cached_normalized_settings

    clear_secret("speech_api_key")
    clear_secret("llm_api_key")

    result = await db.execute(select(Setting).where(Setting.key == _SETTINGS_KEY))
    record = result.scalar_one_or_none()

    if record is None:
        normalized = dict(_DEFAULT_SETTINGS)
    else:
        normalized = _normalize_settings(record.value)

    if record is None:
        db.add(Setting(key=_SETTINGS_KEY, value=normalized))
    else:
        record.value = normalized

    await db.commit()
    _cached_normalized_settings = dict(normalized)
    return _decorate_settings(normalized)


async def update_settings(
    db: AsyncSession,
    *,
    enable_transcription_trace: bool,
    enable_text_input_mode: bool,
    email_sync_interval_minutes: int,
    app_api_base_url: str,
    app_ws_url: str,
    email_provider: str,
    m365_client_id: str,
    m365_tenant_id: str,
    m365_redirect_url: str,
    gmail_client_id: str,
    gmail_client_secret: str | None,
    gmail_redirect_url: str,
    speech_provider: str,
    speech_model: str,
    speech_base_url: str,
    speech_api_key: str | None,
    llm_provider: str,
    llm_model: str,
    llm_base_url: str,
    llm_api_key: str | None,
) -> dict:
    global _cached_normalized_settings

    result = await db.execute(select(Setting).where(Setting.key == _SETTINGS_KEY))
    record = result.scalar_one_or_none()

    llm_provider_normalized = str(llm_provider).strip().lower() or "openai"
    if llm_provider_normalized not in {"openai", "openrouter", "local"}:
        llm_provider_normalized = "openai"

    speech_provider_normalized = str(speech_provider).strip().lower() or "openai"
    if speech_provider_normalized not in {"openai", "openrouter", "local"}:
        speech_provider_normalized = "openai"

    canonical_api_base_url = _validate_configured_api_base_url(app_api_base_url)
    canonical_ws_url = _validate_configured_ws_url(app_ws_url, api_base_url=canonical_api_base_url)
    normalized_sync_interval_minutes = _normalize_sync_interval_minutes(email_sync_interval_minutes)
    email_provider_normalized = str(email_provider).strip().lower() or "m365"
    if email_provider_normalized not in {"m365", "gmail"}:
        email_provider_normalized = "m365"

    normalized = {
        "enable_transcription_trace": bool(enable_transcription_trace),
        "enable_text_input_mode": bool(enable_text_input_mode),
        "email_sync_interval_minutes": normalized_sync_interval_minutes,
        "app_api_base_url": canonical_api_base_url,
        "app_ws_url": canonical_ws_url,
        "email_provider": email_provider_normalized,
        "m365_client_id": str(m365_client_id),
        "m365_tenant_id": str(m365_tenant_id),
        "m365_redirect_url": str(m365_redirect_url).strip() or _DEFAULT_REDIRECT_URL,
        "gmail_client_id": str(gmail_client_id),
        "gmail_redirect_url": str(gmail_redirect_url).strip() or _DEFAULT_GMAIL_REDIRECT_URL,
        "speech_provider": speech_provider_normalized,
        "speech_model": str(speech_model).strip() or _DEFAULT_SPEECH_MODEL,
        "speech_base_url": str(speech_base_url).strip() or _default_base_url(speech_provider_normalized),
        "llm_provider": llm_provider_normalized,
        "llm_model": str(llm_model).strip(),
        "llm_base_url": str(llm_base_url).strip() or _default_base_url(llm_provider_normalized),
    }

    if speech_api_key is not None:
        if str(speech_api_key).strip():
            set_secret("speech_api_key", str(speech_api_key))
        else:
            clear_secret("speech_api_key")

    if gmail_client_secret is not None:
        if str(gmail_client_secret).strip():
            set_secret(_GMAIL_CLIENT_SECRET_NAME, str(gmail_client_secret))
        else:
            clear_secret(_GMAIL_CLIENT_SECRET_NAME)

    if llm_api_key is not None:
        if str(llm_api_key).strip():
            set_secret("llm_api_key", str(llm_api_key))
        else:
            clear_secret("llm_api_key")

    if record is None:
        db.add(Setting(key=_SETTINGS_KEY, value=normalized))
    else:
        record.value = normalized

    await db.commit()
    _cached_normalized_settings = dict(normalized)
    gmail_secret_configured = _has_gmail_client_secret()
    if gmail_client_secret is not None:
        gmail_secret_configured = bool(str(gmail_client_secret).strip())
    return _decorate_settings(normalized, gmail_client_secret_configured=gmail_secret_configured)
