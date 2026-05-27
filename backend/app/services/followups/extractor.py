"""LLM-backed extractor for follow-up obligations with safe heuristic fallback.

Compatibility note:
- Uses OpenAI Responses API as primary path (gpt-5.4-mini compatible).
- Falls back to chat completions for providers/endpoints that do not expose Responses API.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import re

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.runtime_config import get_llm_config
from ...prompts.loader import load_prompt
from ..ai.response_parsing import extract_output_text_from_chat_payload, extract_output_text_from_responses_payload
from ..ai.usage import LlmUsage, extract_llm_usage
from ..email.context import preprocess_incoming_email_context
from ..http_headers import build_json_headers


_ACTION_PATTERNS = (
    "please",
    "can you",
    "could you",
    "need you",
    "would you",
    "review",
    "approve",
    "confirm",
    "send",
    "reply",
    "respond",
)

_URGENT_HINTS = {
    "asap": 1,
    "urgent": 1,
    "today": 3,
    "eod": 3,
    "tomorrow": 12,
}


@dataclass(slots=True)
class ExtractedFollowUp:
    requires_follow_up: bool
    summary: str
    requested_action: str | None
    confidence: float
    first_reminder_after: timedelta
    extracted_due_at: datetime | None
    reasoning: str
    usage: LlmUsage | None = None


class FollowUpExtractionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requires_follow_up: bool
    summary: str = Field(max_length=160)
    requested_action: str
    confidence: float = Field(ge=0, le=1)
    first_reminder_hours: int = Field(ge=1, le=168)
    extracted_due_at: str | None = None
    reasoning: str = Field(max_length=240)


_DEFAULT_SYSTEM_PROMPT = """You analyze email subject + preview and decide if user follow-up is required.
Return ONLY strict JSON object with keys:
- requires_follow_up: boolean
- summary: string (max 160 chars)
- requested_action: string
- confidence: number between 0 and 1
- first_reminder_hours: integer between 1 and 168
- extracted_due_at: ISO8601 datetime string in UTC or null
- reasoning: short string
Rules:
- requires_follow_up=true only if sender asks/needs an action or response from user.
- Keep summary concise and actionable.
- If uncertain, reduce confidence and prefer requires_follow_up=false.
"""

_SYSTEM_PROMPT_NAME = "follow_up_extractor_system.v1.md"
_FOLLOW_UP_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "requires_follow_up",
        "summary",
        "requested_action",
        "confidence",
        "first_reminder_hours",
        "extracted_due_at",
        "reasoning",
    ],
    "properties": {
        "requires_follow_up": {"type": "boolean"},
        "summary": {"type": "string", "maxLength": 160},
        "requested_action": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "first_reminder_hours": {"type": "integer", "minimum": 1, "maximum": 168},
        "extracted_due_at": {
            "anyOf": [
                {"type": "string"},
                {"type": "null"},
            ]
        },
        "reasoning": {"type": "string", "maxLength": 240},
    },
}


def _load_system_prompt() -> str:
    return load_prompt(_SYSTEM_PROMPT_NAME, default_text=_DEFAULT_SYSTEM_PROMPT)


def _parse_iso_utc(value: str | None) -> datetime | None:
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _first_sentence(text: str) -> str:
    candidate = text.strip()
    if not candidate:
        return ""

    for sep in (". ", "? ", "! ", "\n"):
        idx = candidate.find(sep)
        if idx > 0:
            candidate = candidate[:idx + 1].strip()
            break

    return candidate[:240].strip()


def _extract_follow_up_heuristic(subject: str, body_preview: str, received_at: datetime) -> ExtractedFollowUp:
    subject_clean = (subject or "").strip()
    preview_clean = (body_preview or "").strip()
    combined = f"{subject_clean}\n{preview_clean}".strip()
    normalized = combined.lower()

    has_question = "?" in combined
    has_action_pattern = any(pattern in normalized for pattern in _ACTION_PATTERNS)
    has_urgent_hint = any(hint in normalized for hint in _URGENT_HINTS)

    requires_follow_up = has_question or has_action_pattern

    confidence = 0.35
    if requires_follow_up:
        confidence = 0.65
    if has_question and has_action_pattern:
        confidence += 0.15
    if has_urgent_hint:
        confidence += 0.1
    confidence = max(0.0, min(0.99, confidence))

    first_reminder_after = timedelta(hours=24)
    for hint, hours in _URGENT_HINTS.items():
        if hint in normalized:
            first_reminder_after = timedelta(hours=hours)
            break

    extracted_due_at: datetime | None = None
    if "tomorrow" in normalized:
        extracted_due_at = received_at + timedelta(days=1)

    explicit_date = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", normalized)
    if explicit_date:
        try:
            extracted_due_at = datetime.fromisoformat(explicit_date.group(1)).replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            pass

    summary = subject_clean or _first_sentence(preview_clean) or "Email may require follow-up"

    requested_action: str | None = None
    if requires_follow_up:
        requested_action = _first_sentence(preview_clean) or "Review email and respond"

    reasoning = (
        f"question={has_question}; action_pattern={has_action_pattern}; "
        f"urgent_hint={has_urgent_hint}"
    )

    return ExtractedFollowUp(
        requires_follow_up=requires_follow_up,
        summary=summary,
        requested_action=requested_action,
        confidence=confidence,
        first_reminder_after=first_reminder_after,
        extracted_due_at=extracted_due_at,
        reasoning=f"heuristic:{reasoning}",
    )


def _json_payload_to_extracted(payload: dict, received_at: datetime, *, usage: LlmUsage | None = None) -> ExtractedFollowUp:
    try:
        validated = FollowUpExtractionPayload.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"LLM payload validation failed: {exc}") from exc

    requires_follow_up = validated.requires_follow_up
    summary = validated.summary.strip()[:160] or "Email may require follow-up"
    requested_action_raw = validated.requested_action.strip()
    requested_action = requested_action_raw or None

    confidence = float(validated.confidence)
    confidence = max(0.0, min(0.99, confidence))

    first_reminder_hours = int(validated.first_reminder_hours)
    first_reminder_hours = max(1, min(168, first_reminder_hours))

    extracted_due_at = _parse_iso_utc(validated.extracted_due_at)
    if extracted_due_at is None and isinstance(validated.extracted_due_at, str):
        # Keep a mild heuristic fallback for short expressions like "tomorrow" in model text.
        if "tomorrow" in validated.extracted_due_at.lower():
            extracted_due_at = received_at + timedelta(days=1)

    reasoning = validated.reasoning.strip()[:240] or "llm"

    return ExtractedFollowUp(
        requires_follow_up=requires_follow_up,
        summary=summary,
        requested_action=requested_action,
        confidence=confidence,
        first_reminder_after=timedelta(hours=first_reminder_hours),
        extracted_due_at=extracted_due_at,
        reasoning=f"llm:{reasoning}",
        usage=usage,
    )


def _extract_json_text_from_llm_response(data: dict) -> str:
    return extract_output_text_from_chat_payload(
        data,
        missing_choices_message="LLM response missing choices",
        missing_message_message="LLM response missing message",
        missing_text_message="Unsupported LLM response content format",
    )


def _extract_json_text_from_responses_api_response(data: dict) -> str:
    return extract_output_text_from_responses_payload(
        data,
        missing_message="Responses API output missing output_text",
    )


async def _call_responses_api(
    *,
    endpoint: str,
    headers: dict[str, str],
    model: str,
    user_prompt: str,
) -> dict:
    system_prompt = _load_system_prompt()
    payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": system_prompt}],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": user_prompt}],
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "follow_up_extraction",
                "schema": _FOLLOW_UP_JSON_SCHEMA,
                "strict": True,
            }
        },
        "temperature": 0,
    }

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(endpoint, headers=headers, json=payload)
        response.raise_for_status()
    return response.json()


async def _call_chat_completions_api(
    *,
    endpoint: str,
    headers: dict[str, str],
    model: str,
    user_prompt: str,
) -> dict:
    system_prompt = _load_system_prompt()
    payload = {
        "model": model,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0,
    }

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(endpoint, headers=headers, json=payload)
        response.raise_for_status()
    return response.json()


async def extract_follow_up(
    db: AsyncSession,
    subject: str,
    body_preview: str,
    received_at: datetime,
) -> ExtractedFollowUp:
    """Extract follow-up intent using LLM; fallback to heuristic on any failure."""
    compact = preprocess_incoming_email_context(subject=subject, body_preview=body_preview)
    heuristic = _extract_follow_up_heuristic(compact.subject, compact.body_preview, received_at)

    try:
        config = await get_llm_config(db)
        model = config.model or "gpt-5.4-mini"
        base_url = config.base_url.rstrip("/")
        headers = build_json_headers(config.api_key)

        user_prompt = (
            "Email subject:\n"
            f"{compact.subject}\n\n"
            "Email body preview:\n"
            f"{compact.body_preview}\n\n"
            f"Received at (UTC): {received_at.astimezone(timezone.utc).isoformat()}"
        )

        content_text = ""
        provider = (config.provider or "").lower()
        responses_json: dict | None = None
        completions_json: dict | None = None

        # Primary path: OpenAI Responses API (recommended for gpt-5.4-mini).
        responses_error: Exception | None = None
        if provider == "openai":
            try:
                responses_json = await _call_responses_api(
                    endpoint=f"{base_url}/responses",
                    headers=headers,
                    model=model,
                    user_prompt=user_prompt,
                )
                content_text = _extract_json_text_from_responses_api_response(responses_json)
            except Exception as exc:
                responses_error = exc

        # Fallback path: chat completions (OpenRouter/local compatibility).
        if not content_text:
            completions_json = await _call_chat_completions_api(
                endpoint=f"{base_url}/chat/completions",
                headers=headers,
                model=model,
                user_prompt=user_prompt,
            )
            content_text = _extract_json_text_from_llm_response(completions_json)

        extracted_payload = json.loads(content_text)
        usage_payload = responses_json if responses_json is not None and content_text and responses_error is None else completions_json
        usage = extract_llm_usage(
            usage_payload or {},
            prompt_text=user_prompt,
            completion_text=content_text,
        )
        extracted = _json_payload_to_extracted(extracted_payload, received_at, usage=usage)
        if responses_error is not None:
            extracted.reasoning = f"{extracted.reasoning}; responses_fallback={type(responses_error).__name__}"
        return extracted
    except Exception as exc:
        return ExtractedFollowUp(
            requires_follow_up=heuristic.requires_follow_up,
            summary=heuristic.summary,
            requested_action=heuristic.requested_action,
            confidence=heuristic.confidence,
            first_reminder_after=heuristic.first_reminder_after,
            extracted_due_at=heuristic.extracted_due_at,
            reasoning=f"{heuristic.reasoning}; llm_fallback={type(exc).__name__}",
            usage=None,
        )
