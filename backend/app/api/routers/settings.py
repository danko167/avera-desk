from __future__ import annotations

import logging
import httpx
import os
from fastapi import APIRouter, HTTPException, Query
from urllib.parse import urlparse

from ...core.logging import log_exception
from ...core.url_validation import is_private_or_loopback_host, normalize_http_or_https_url
from ...core.secret_store import get_secret
from ...core.transcription_trace import set_trace_enabled
from ...db import db_session
from ...schemas import (
    AppSettings,
    ConversationTurn,
    LlmUsageSummary,
    TestAiConnectionRequest,
    TestAiConnectionResult,
    UpdateAppSettings,
)
from ...services.ai.response_parsing import extract_output_text_from_chat_payload, extract_output_text_from_responses_payload
from ...services.ai.usage_store import get_llm_usage_summary
from ...services.http_headers import build_json_headers
from ...services import shared

router = APIRouter()
logger = logging.getLogger(__name__)


def _is_public_ai_test_base_url_allowed() -> bool:
    if os.getenv("PYTEST_CURRENT_TEST"):
        return True
    return str(os.getenv("AVERA_ALLOW_PUBLIC_AI_TEST_BASE_URL", "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _is_external_ai_provider(provider: str) -> bool:
    return provider in {"openai", "openrouter"}


def _normalize_base_url(value: str, *, provider: str) -> str:
    normalized = normalize_http_or_https_url(value, preserve_path=True)
    parsed = urlparse(normalized)

    # Public HTTPS hosts are expected for external providers (OpenAI/OpenRouter).
    if _is_external_ai_provider(provider):
        if parsed.scheme != "https" and not is_private_or_loopback_host(parsed.hostname):
            raise ValueError("Public base_url values for external providers must use https://")
        return normalized

    if _is_public_ai_test_base_url_allowed():
        return normalized

    if not is_private_or_loopback_host(parsed.hostname):
        raise ValueError(
            "base_url host must be loopback/private for local security. "
            "Set AVERA_ALLOW_PUBLIC_AI_TEST_BASE_URL=1 to allow public hosts."
        )

    return normalized


async def _check_llm_connection(payload: TestAiConnectionRequest) -> TestAiConnectionResult:
    provider = payload.provider.lower()
    model = payload.model.strip()
    if not model:
        raise HTTPException(status_code=400, detail="Model is required.")

    try:
        base_url = _normalize_base_url(payload.base_url, provider=provider)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    headers = build_json_headers(payload.api_key or get_secret("llm_api_key"))
    prompt = "Reply with exactly: ok"
    responses_data: dict | None = None
    completions_data: dict | None = None
    responses_error: Exception | None = None

    responses_payload = {
        "model": model,
        "input": [
            {
                "role": "user",
                "content": [{"type": "input_text", "text": prompt}],
            }
        ],
        "temperature": 0,
    }
    chat_payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=5.0, read=20.0, write=10.0, pool=5.0)) as client:
            if provider == "openai":
                try:
                    resp = await client.post(f"{base_url}/responses", headers=headers, json=responses_payload)
                    resp.raise_for_status()
                    responses_data = resp.json()
                except Exception as exc:
                    log_exception(
                        logger,
                        "llm_connection_responses_fallback",
                        exc,
                        provider=provider,
                        model=model,
                        base_url=base_url,
                        endpoint="/responses",
                    )
                    responses_error = exc

            if responses_data is None:
                resp = await client.post(f"{base_url}/chat/completions", headers=headers, json=chat_payload)
                resp.raise_for_status()
                completions_data = resp.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"LLM connection test failed: {exc.response.status_code} {exc.response.reason_phrase}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"LLM connection test failed: {exc}") from exc

    try:
        if responses_data is not None:
            endpoint = "/responses"
            extract_output_text_from_responses_payload(responses_data)
            detail = "Connection test succeeded via Responses API."
        else:
            endpoint = "/chat/completions"
            extract_output_text_from_chat_payload(completions_data or {})
            if responses_error is not None:
                detail = f"Connection test succeeded via chat completions after Responses fallback: {type(responses_error).__name__}."
            else:
                detail = "Connection test succeeded via chat completions."
    except Exception as exc:
        log_exception(
            logger,
            "llm_connection_invalid_response",
            exc,
            provider=provider,
            model=model,
            base_url=base_url,
            endpoint=endpoint,
        )
        raise HTTPException(status_code=502, detail=f"LLM connection test returned an invalid response: {exc}") from exc

    return TestAiConnectionResult(ok=True, provider=provider, model=model, base_url=base_url, endpoint=endpoint, detail=detail)


@router.get("/settings", response_model=AppSettings)
async def get_settings() -> AppSettings:
    async with db_session() as db:
        values = await shared.get_settings(db)
    return AppSettings(**values)


@router.put("/settings", response_model=AppSettings)
async def put_settings(payload: UpdateAppSettings) -> AppSettings:
    try:
        async with db_session() as db:
            values = await shared.update_settings(
                db,
                enable_transcription_trace=payload.enable_transcription_trace,
                enable_text_input_mode=payload.enable_text_input_mode,
                email_sync_interval_minutes=payload.email_sync_interval_minutes,
                app_api_base_url=payload.app_api_base_url,
                app_ws_url=payload.app_ws_url,
                email_provider=payload.email_provider,
                m365_client_id=payload.m365_client_id,
                m365_tenant_id=payload.m365_tenant_id,
                m365_redirect_url=payload.m365_redirect_url,
                gmail_client_id=payload.gmail_client_id,
                gmail_client_secret=payload.gmail_client_secret,
                gmail_redirect_url=payload.gmail_redirect_url,
                speech_provider=payload.speech_provider,
                speech_model=payload.speech_model,
                speech_base_url=payload.speech_base_url,
                speech_api_key=payload.speech_api_key,
                llm_provider=payload.llm_provider,
                llm_model=payload.llm_model,
                llm_base_url=payload.llm_base_url,
                llm_api_key=payload.llm_api_key,
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    set_trace_enabled(values.get("enable_transcription_trace", False))
    return AppSettings(**values)


@router.post("/settings/test-ai-connection", response_model=TestAiConnectionResult)
async def test_ai_connection(payload: TestAiConnectionRequest) -> TestAiConnectionResult:
    return await _check_llm_connection(payload)


@router.post("/settings/clear-ai-secrets")
async def clear_ai_secrets() -> dict[str, bool]:
    async with db_session() as db:
        await shared.clear_ai_secrets(db)
    return {"cleared": True}


@router.get("/settings/llm-usage-summary", response_model=LlmUsageSummary)
async def get_llm_usage_totals() -> LlmUsageSummary:
    async with db_session() as db:
        summary = await get_llm_usage_summary(db)
    return LlmUsageSummary(**summary)


@router.get("/conversation-turns", response_model=list[ConversationTurn])
async def get_conversation_turns(limit: int = Query(default=200, ge=1, le=1000)) -> list[ConversationTurn]:
    async with db_session() as db:
        turns = await shared.get_recent_conversation_turns(db, limit=limit)
    return turns
