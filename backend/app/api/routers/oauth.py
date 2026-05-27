from __future__ import annotations

from html import escape
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from ...db import db_session
from ...integrations.email_provider import get_oauth_module, normalize_email_provider
from ...schemas import OAuthStatus
from ...services import shared

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/oauth/login-url")
async def get_oauth_login_url() -> dict[str, str]:
    try:
        async with db_session() as db:
            settings = await shared.get_settings(db)
            email_provider = normalize_email_provider(settings.get("email_provider"))
            oauth = get_oauth_module(email_provider)
            login_url = await oauth.get_auth_url(db)
    except RuntimeError as exc:
        oauth_error = getattr(exc, "missing_settings", None)
        if oauth_error is not None:
            raise HTTPException(
                status_code=400,
                detail={"code": "oauth_setup_required", "missing_settings": oauth_error},
            ) from exc
        raise
    return {"login_url": login_url}


@router.get("/oauth/callback")
async def oauth_callback(request: Request):
    auth_response = {key: value for key, value in request.query_params.items()}
    return await _handle_oauth_callback(auth_response, email_provider="m365", provider_label="Microsoft")


@router.get("/oauth/google/callback")
async def oauth_google_callback(request: Request):
    auth_response = {key: value for key, value in request.query_params.items()}
    return await _handle_oauth_callback(auth_response, email_provider="gmail", provider_label="Gmail")


@router.post("/oauth/callback")
async def oauth_callback_post(request: Request):
    form = await request.form()
    auth_response = {key: str(value) for key, value in form.items()}
    return await _handle_oauth_callback(auth_response, email_provider="m365", provider_label="Microsoft")


@router.post("/oauth/google/callback")
async def oauth_google_callback_post(request: Request):
    form = await request.form()
    auth_response = {key: str(value) for key, value in form.items()}
    return await _handle_oauth_callback(auth_response, email_provider="gmail", provider_label="Gmail")


async def _handle_oauth_callback(
    auth_response: dict[str, str],
    *,
    email_provider: str,
    provider_label: str,
) -> HTMLResponse:
    if auth_response.get("error"):
        description = str(auth_response.get("error_description", "Unknown OAuth error")).strip() or "Unknown OAuth error"
        logger.warning("oauth_callback_error description=%s", description)
        safe_description = escape(description, quote=True)
        return HTMLResponse(
            content=(
                "<html><body style='font-family: sans-serif; padding: 16px;'>"
                f"<h3>{provider_label} connection failed</h3>"
                f"<p>{safe_description}</p>"
                "<p>You can close this window.</p>"
                "<script>setTimeout(() => window.close(), 1200);</script>"
                "</body></html>"
            ),
            status_code=400,
        )

    async with db_session() as db:
        oauth = get_oauth_module(email_provider)
        result = await oauth.exchange_auth_response(auth_response, db)

    if result:
        return HTMLResponse(
            content=(
                "<html><body style='font-family: sans-serif; padding: 16px;'>"
                f"<h3>{provider_label} connected</h3>"
                "<p>You can close this window.</p>"
                "<script>setTimeout(() => window.close(), 800);</script>"
                "</body></html>"
            ),
            status_code=200,
        )

    return HTMLResponse(
        content=(
            "<html><body style='font-family: sans-serif; padding: 16px;'>"
            f"<h3>{provider_label} connection failed</h3>"
            "<p>Token exchange failed. Please try again.</p>"
            "<p>You can close this window.</p>"
            "<script>setTimeout(() => window.close(), 1200);</script>"
            "</body></html>"
        ),
        status_code=400,
    )


@router.get("/oauth/status", response_model=OAuthStatus)
async def oauth_status(resolve_mailbox: bool = False) -> OAuthStatus:
    missing_settings: list[str] = []

    def append_missing(name: str) -> None:
        if name not in missing_settings:
            missing_settings.append(name)

    async with db_session() as db:
        settings = await shared.get_settings(db)
        email_provider = normalize_email_provider(settings.get("email_provider"))
        oauth = get_oauth_module(email_provider)
        oauth_missing_settings = await oauth.get_missing_required_settings(db)

        for key in oauth_missing_settings:
            append_missing(key)

        speech_provider = str(settings.get("speech_provider", "openai")).strip().lower()
        llm_provider = str(settings.get("llm_provider", "openai")).strip().lower()
        speech_api_key_configured = bool(settings.get("speech_api_key_configured", False))
        llm_api_key_configured = bool(settings.get("llm_api_key_configured", False))

        if speech_provider in {"openai", "openrouter"} and not speech_api_key_configured:
            append_missing("speech_api_key")

        if llm_provider in {"openai", "openrouter"} and not llm_api_key_configured:
            append_missing("llm_api_key")

        oauth_setup_required = len(oauth_missing_settings) > 0
        setup_required = len(missing_settings) > 0
        authenticated = oauth.is_authenticated() and not oauth_setup_required
        connected_mailbox: str | None = None

        # Mailbox identity lookup can block on external provider/network issues.
        # Keep startup fast and reliable by making it opt-in for callers that need it.
        if authenticated and resolve_mailbox:
            try:
                connected_mailbox = await oauth.get_authenticated_mailbox(db)
            except (RuntimeError, ValueError) as exc:
                logger.warning("oauth_mailbox_lookup_failed error=%s", exc)
                authenticated = False
                setup_required = True
                if not oauth_missing_settings:
                    oauth_missing_settings = await oauth.get_missing_required_settings(db)
                for key in oauth_missing_settings:
                    append_missing(key)

    return OAuthStatus(
        authenticated=authenticated,
        connected_mailbox=connected_mailbox,
        persistence=oauth.get_token_persistence(),
        setup_required=setup_required,
        missing_settings=missing_settings,
    )


@router.post("/oauth/logout")
async def oauth_logout() -> dict[str, str]:
    async with db_session() as db:
        settings = await shared.get_settings(db)
    email_provider = normalize_email_provider(settings.get("email_provider"))
    oauth = get_oauth_module(email_provider)
    oauth.logout()
    return {"status": "logged out"}
