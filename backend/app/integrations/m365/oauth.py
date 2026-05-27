"""OAuth 2.0 PKCE flow for Microsoft 365 Outlook access."""

import base64
import logging
import os
import time
from urllib.parse import urlparse
from typing import TYPE_CHECKING

import httpx
import msal

try:
    import keyring
except ImportError:  # pragma: no cover - depends on local runtime environment
    keyring = None

try:
    from keyring.errors import KeyringError
except ImportError:  # pragma: no cover - depends on local runtime environment
    KeyringError = RuntimeError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


_cached_config: dict | None = None
_fallback_refresh_token: str | None = None
_SCOPES = [
    "https://graph.microsoft.com/Mail.Read",
    "https://graph.microsoft.com/Mail.Send",
    "https://graph.microsoft.com/People.Read",
    "https://graph.microsoft.com/Calendars.Read",
    "https://graph.microsoft.com/Calendars.ReadWrite",
    "https://graph.microsoft.com/User.Read",
]
_pending_auth_flows: dict[str, tuple[dict, float]] = {}
_keyring_write_failed = False
_KEYRING_SERVICE = "avera_desk"
_TOKEN_USER = "m365_refresh_token"
_TOKEN_CHUNK_COUNT_USER = "m365_refresh_token_chunk_count"
_TOKEN_CHUNK_PREFIX = "m365_refresh_token_chunk_"
_PENDING_AUTH_FLOW_TTL_SECONDS = 10 * 60
_MAX_PENDING_AUTH_FLOWS = 256
# Windows Credential Manager limits credential blobs to 2560 bytes.
# Keep chunks safely below that (UTF-16 can use ~2 bytes per character).
_KEYRING_CHUNK_SIZE = 1000
logger = logging.getLogger(__name__)
_KEYRING_OPERATION_ERRORS = (KeyringError, RuntimeError)


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


def _is_valid_redirect_uri(value: str) -> bool:
    try:
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except ValueError:
        return False


def _is_valid_tenant_id(value: str) -> bool:
    tenant = value.strip()
    if not tenant:
        return False
    if "/" in tenant or " " in tenant:
        return False
    return True


def _encode_token_for_storage(token: str) -> str:
    return base64.urlsafe_b64encode(token.encode("utf-8")).decode("ascii")


def _decode_token_from_storage(value: str) -> str:
    try:
        return base64.urlsafe_b64decode(value.encode("ascii")).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        # Backward compatibility for previously stored plain tokens.
        return value


def _read_chunked_refresh_token_from_keyring() -> str | None:
    if keyring is None:
        return None
    count_raw = keyring.get_password(_KEYRING_SERVICE, _TOKEN_CHUNK_COUNT_USER)
    if not count_raw:
        return None
    try:
        count = int(count_raw)
    except ValueError:
        return None
    if count <= 0:
        return None

    parts: list[str] = []
    for idx in range(count):
        part = keyring.get_password(_KEYRING_SERVICE, f"{_TOKEN_CHUNK_PREFIX}{idx}")
        if part is None:
            return None
        parts.append(part)
    return _decode_token_from_storage("".join(parts))


def _clear_refresh_token_from_keyring() -> None:
    if keyring is None:
        return

    try:
        count_raw = keyring.get_password(_KEYRING_SERVICE, _TOKEN_CHUNK_COUNT_USER)
    except _KEYRING_OPERATION_ERRORS as exc:
        logger.debug("oauth_keyring_read_chunk_count_failed error=%s", exc)
        count_raw = None

    if count_raw:
        try:
            count = int(count_raw)
        except ValueError:
            count = 0
        for idx in range(max(count, 0)):
            try:
                keyring.delete_password(_KEYRING_SERVICE, f"{_TOKEN_CHUNK_PREFIX}{idx}")
            except _KEYRING_OPERATION_ERRORS as exc:
                logger.debug("oauth_keyring_delete_chunk_failed index=%s error=%s", idx, exc)
        try:
            keyring.delete_password(_KEYRING_SERVICE, _TOKEN_CHUNK_COUNT_USER)
        except _KEYRING_OPERATION_ERRORS as exc:
            logger.debug("oauth_keyring_delete_chunk_count_failed error=%s", exc)

    try:
        keyring.delete_password(_KEYRING_SERVICE, _TOKEN_USER)
    except _KEYRING_OPERATION_ERRORS as exc:
        logger.debug("oauth_keyring_delete_primary_token_failed error=%s", exc)


def _get_refresh_token() -> str | None:
    """Read refresh token from keychain when available, else in-memory fallback."""
    global _fallback_refresh_token
    if keyring is None:
        return _fallback_refresh_token
    try:
        token = keyring.get_password(_KEYRING_SERVICE, _TOKEN_USER)
        if token:
            return _decode_token_from_storage(token)

        token = _read_chunked_refresh_token_from_keyring()
        return token or _fallback_refresh_token
    except _KEYRING_OPERATION_ERRORS as exc:  # pragma: no cover - OS/keyring backend dependent
        logger.warning("oauth_keyring_read_failed_using_memory error=%s", exc)
        return _fallback_refresh_token


def get_token_persistence() -> str:
    """Report whether the current token survives app termination."""
    global _fallback_refresh_token

    if keyring is not None:
        try:
            token = keyring.get_password(_KEYRING_SERVICE, _TOKEN_USER)
            if token:
                return "persistent"

            token = _read_chunked_refresh_token_from_keyring()
            if token:
                return "persistent"
        except _KEYRING_OPERATION_ERRORS as exc:  # pragma: no cover - OS/keyring backend dependent
            logger.warning("oauth_keyring_persistence_check_failed error=%s", exc)

    if _fallback_refresh_token:
        return "session"

    return "none"


def _set_refresh_token(token: str) -> bool:
    """Persist refresh token in keychain when available, else in-memory fallback."""
    global _fallback_refresh_token, _keyring_write_failed
    if keyring is None:
        _fallback_refresh_token = token
        return False
    try:
        _clear_refresh_token_from_keyring()

        encoded = _encode_token_for_storage(token)

        if len(encoded) <= _KEYRING_CHUNK_SIZE:
            keyring.set_password(_KEYRING_SERVICE, _TOKEN_USER, encoded)
        else:
            parts = [
                encoded[i:i + _KEYRING_CHUNK_SIZE]
                for i in range(0, len(encoded), _KEYRING_CHUNK_SIZE)
            ]
            keyring.set_password(_KEYRING_SERVICE, _TOKEN_CHUNK_COUNT_USER, str(len(parts)))
            for idx, part in enumerate(parts):
                keyring.set_password(_KEYRING_SERVICE, f"{_TOKEN_CHUNK_PREFIX}{idx}", part)

        _fallback_refresh_token = token
        _keyring_write_failed = False
        return True
    except _KEYRING_OPERATION_ERRORS as exc:  # pragma: no cover - OS/keyring backend dependent
        if not _keyring_write_failed:
            logger.warning("oauth_keyring_write_failed_using_memory error=%s", exc)
            _keyring_write_failed = True
        _fallback_refresh_token = token
        return False


def _clear_refresh_token() -> None:
    """Delete refresh token from keychain or clear in-memory fallback."""
    global _fallback_refresh_token
    if keyring is None:
        _fallback_refresh_token = None
        return
    try:
        _clear_refresh_token_from_keyring()
    except _KEYRING_OPERATION_ERRORS as exc:  # pragma: no cover - OS/keyring backend dependent
        logger.warning("oauth_keyring_delete_failed error=%s", exc)
    finally:
        _fallback_refresh_token = None


async def _get_config(db: "AsyncSession | None" = None) -> dict:
    """Load OAuth config from settings or environment."""
    global _cached_config
    
    # Try to load from DB if available
    if db:
        from ...services.shared.preferences import get_settings
        settings = await get_settings(db)
        tenant_id = str(settings.get("m365_tenant_id", "")).strip()
        _cached_config = {
            "client_id": settings.get("m365_client_id", ""),
            "tenant_id": tenant_id,
            "authority": f"https://login.microsoftonline.com/{tenant_id or 'common'}",
            "redirect_uri": settings.get("m365_redirect_url", "http://localhost:8000/api/oauth/callback"),
        }
        return _cached_config
    
    # Fall back to cached or environment
    if _cached_config:
        return _cached_config
    
    tenant_id = str(os.getenv("M365_TENANT_ID", "")).strip()
    return {
        "client_id": os.getenv("M365_CLIENT_ID", ""),
        "tenant_id": tenant_id,
        "authority": f"https://login.microsoftonline.com/{tenant_id or 'common'}",
        "redirect_uri": os.getenv("M365_REDIRECT_URL", "http://localhost:8000/api/oauth/callback"),
    }


async def get_missing_required_settings(db: "AsyncSession | None" = None) -> list[str]:
    """Return required OAuth setting names that are missing or invalid."""
    config = await _get_config(db)
    missing: list[str] = []

    client_id = str(config.get("client_id", "")).strip()
    tenant_id = str(config.get("tenant_id", "")).strip()
    redirect_uri = str(config.get("redirect_uri", "")).strip()

    if not client_id:
        missing.append("m365_client_id")
    if not _is_valid_tenant_id(tenant_id):
        missing.append("m365_tenant_id")
    if not _is_valid_redirect_uri(redirect_uri):
        missing.append("m365_redirect_url")

    return missing


async def get_msal_app(db: "AsyncSession | None" = None) -> msal.PublicClientApplication:
    """Initialize MSAL public client (desktop app, no client secret needed)."""
    missing = await get_missing_required_settings(db)
    if missing:
        raise OAuthSetupRequiredError(missing)

    config = await _get_config(db)
    return msal.PublicClientApplication(
        client_id=config["client_id"],
        authority=config["authority"],
    )


async def get_auth_url(db: "AsyncSession | None" = None) -> str:
    """Generate the OAuth login URL."""
    app = await get_msal_app(db)
    config = await _get_config(db)

    # Create an auth flow object that includes PKCE verifier/challenge data.
    auth_flow = app.initiate_auth_code_flow(
        scopes=_SCOPES,
        redirect_uri=config["redirect_uri"],
        response_mode="form_post",
    )

    state = auth_flow.get("state")
    auth_uri = auth_flow.get("auth_uri")
    if not state or not auth_uri:
        raise RuntimeError("Failed to initialize OAuth authorization flow")

    _prune_pending_auth_flows()
    _pending_auth_flows[state] = (auth_flow, time.monotonic())
    return auth_uri


async def exchange_auth_response(auth_response: dict[str, str], db: "AsyncSession | None" = None) -> dict | None:
    """Exchange OAuth callback response for tokens using stored PKCE flow."""
    app = await get_msal_app(db)
    state = auth_response.get("state", "")
    if not state:
        logger.warning("oauth_callback_missing_state")
        return None

    _prune_pending_auth_flows()
    pending_entry = _pending_auth_flows.pop(state, None)
    auth_flow = pending_entry[0] if pending_entry is not None else None
    if not auth_flow:
        logger.warning("oauth_callback_flow_not_found_or_expired")
        return None

    result = app.acquire_token_by_auth_code_flow(auth_flow, auth_response)

    if "error" in result:
        logger.warning("oauth_callback_error detail=%s", result.get("error_description", result["error"]))
        return None

    # Store refresh token securely in OS keychain
    if "refresh_token" in result:
        saved_in_keyring = _set_refresh_token(result["refresh_token"])
        if saved_in_keyring:
            logger.info("oauth_refresh_token_persisted_keychain")
        elif keyring is None:
            logger.warning("oauth_keyring_missing_token_in_memory_session_only")
        else:
            logger.warning("oauth_refresh_token_in_memory_session_only")

    return {
        "access_token": result.get("access_token"),
        "expires_at": result.get("expires_in"),
    }


async def get_access_token(db: "AsyncSession | None" = None) -> str | None:
    """Get valid access token, refreshing if needed."""
    try:
        app = await get_msal_app(db)
    except OAuthSetupRequiredError:
        return None

    # Try to use cached token first
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(
            scopes=_SCOPES,
            account=accounts[0],
        )
        if "access_token" in result:
            return result["access_token"]

    # Try refresh token from keychain
    refresh_token = _get_refresh_token()
    if refresh_token:
        result = app.acquire_token_by_refresh_token(
            refresh_token=refresh_token,
            scopes=_SCOPES,
        )
        if "access_token" in result:
            # Update refresh token if a new one was issued
            if "refresh_token" in result and result["refresh_token"] != refresh_token:
                _set_refresh_token(result["refresh_token"])
            return result["access_token"]
        else:
            # Refresh token expired; user must re-authenticate
            logger.warning("oauth_refresh_token_expired_reauth_required")
            _clear_refresh_token()
            return None

    return None


def is_authenticated() -> bool:
    """Check if user has a valid stored token."""
    refresh_token = _get_refresh_token()
    return refresh_token is not None


def logout() -> None:
    """Clear stored tokens."""
    _clear_refresh_token()
    logger.info("oauth_tokens_cleared")


async def get_authenticated_mailbox(db: "AsyncSession | None" = None) -> str | None:
    """Return mailbox identifier for the currently authenticated user."""
    access_token = await get_access_token(db)
    if not access_token:
        return None

    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://graph.microsoft.com/v1.0/me?$select=displayName,mail,userPrincipalName",
                headers=headers,
                timeout=20,
            )
            response.raise_for_status()

        data = response.json()
        return data.get("mail") or data.get("userPrincipalName")
    except httpx.HTTPError as exc:
        logger.warning("oauth_mailbox_identity_lookup_failed error=%s", exc)
        return None


async def get_authenticated_display_name(db: "AsyncSession | None" = None) -> str | None:
    """Return display name for the currently authenticated user."""
    access_token = await get_access_token(db)
    if not access_token:
        return None

    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://graph.microsoft.com/v1.0/me?$select=displayName",
                headers=headers,
                timeout=20,
            )
            response.raise_for_status()

        data = response.json()
        value = (data.get("displayName") or "").strip()
        return value or None
    except httpx.HTTPError as exc:
        logger.warning("oauth_display_name_lookup_failed error=%s", exc)
        return None
