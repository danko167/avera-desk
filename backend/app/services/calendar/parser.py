from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
import json
import logging
import re

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.runtime_config import get_llm_config
from ...prompts.loader import load_prompt
from ..ai.response_parsing import extract_output_text_from_chat_payload, extract_output_text_from_responses_payload
from ..ai.usage import LlmUsage, extract_llm_usage
from ..http_headers import build_json_headers

logger = logging.getLogger(__name__)

_CALENDAR_CANDIDATE_RE = re.compile(
    r"(?:\b(meeting|calendar|appointment|invite|schedule|reschedule|call|sync)\b)|(?:\bwith\b.+\b(today|tomorrow|tonight|monday|tuesday|wednesday|thursday|friday|saturday|sunday|am|pm)\b)",
    re.IGNORECASE,
)


def _safe_log_text(value: object) -> str:
    return str(value).encode("cp1252", errors="replace").decode("cp1252")


@dataclass(slots=True)
class ParsedCalendarAction:
    action: str  # none | create_event
    title: str
    attendee_queries: list[str]
    desired_start_at: datetime | None
    duration_minutes: int | None
    reasoning: str
    usage: LlmUsage | None = None


class CalendarActionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str = Field(pattern="^(none|create_event)$")
    title: str = Field(default="", max_length=180)
    attendee_queries: list[str] = Field(default_factory=list, max_length=8)
    desired_start_at: str | None = None
    duration_minutes: int | None = Field(default=None, ge=15, le=480)
    reasoning: str = Field(max_length=240)


_DEFAULT_PROMPT = """You interpret a spoken calendar scheduling request.
Return ONLY strict JSON object with keys:
- action: one of \"none\" or \"create_event\"
- title: short event title, or empty string when unknown
- attendee_queries: array of attendee names or emails inferred from the request
- desired_start_at: ISO8601 datetime with timezone offset, or null
- duration_minutes: integer duration in minutes, or null
- reasoning: short string

Rules:
- Choose action=\"create_event\" only when the user is asking to create or schedule a meeting/event/call.
- Choose action=\"none\" for reminders, emails, replies, or unrelated commands.
- Interpret relative time phrases using the provided local datetime.
- When the user gives a time but no duration, default duration_minutes to 30.
- Keep title concise and practical.
- attendee_queries should contain plain names/emails only, without extra wording.
"""

_PROMPT_NAME = "calendar_user_action_system.v1.md"

_ACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["action", "title", "attendee_queries", "desired_start_at", "duration_minutes", "reasoning"],
    "properties": {
        "action": {"type": "string", "enum": ["none", "create_event"]},
        "title": {"type": "string", "maxLength": 180},
        "attendee_queries": {
            "type": "array",
            "items": {"type": "string", "maxLength": 120},
            "maxItems": 8,
        },
        "desired_start_at": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "duration_minutes": {"anyOf": [{"type": "integer", "minimum": 15, "maximum": 480}, {"type": "null"}]},
        "reasoning": {"type": "string", "maxLength": 240},
    },
}


def _prompt() -> str:
    return load_prompt(_PROMPT_NAME, default_text=_DEFAULT_PROMPT)


def _parse_desired_start_at(raw: str | None) -> datetime | None:
    if raw is None:
        return None
    candidate = raw.strip()
    if not candidate:
        return None
    normalized = candidate.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        local_tz = datetime.now().astimezone().tzinfo
        return parsed.replace(tzinfo=local_tz)
    return parsed


def _parse_model_payload(payload: object) -> ParsedCalendarAction:
    try:
        validated = CalendarActionPayload.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"calendar action payload validation failed: {exc}") from exc

    desired_start_at = _parse_desired_start_at(validated.desired_start_at)
    attendee_queries = [item.strip() for item in validated.attendee_queries if item and item.strip()]
    if validated.action == "create_event":
        if desired_start_at is None:
            raise ValueError("create_event action requires desired_start_at")
        if validated.duration_minutes is None:
            raise ValueError("create_event action requires duration_minutes")
    elif desired_start_at is not None or validated.duration_minutes is not None:
        raise ValueError("none action must not provide desired_start_at or duration_minutes")

    return ParsedCalendarAction(
        action=validated.action,
        title=validated.title.strip(),
        attendee_queries=attendee_queries,
        desired_start_at=desired_start_at,
        duration_minutes=validated.duration_minutes,
        reasoning=f"llm:{validated.reasoning.strip() or 'ok'}",
    )


async def _llm_parse_calendar_user_action(utterance: str, config) -> ParsedCalendarAction:
    model = config.model or "gpt-5.4-mini"
    base_url = config.base_url.rstrip("/")
    headers = build_json_headers(config.api_key)
    provider = (config.provider or "").lower()
    local_now = datetime.now().astimezone().isoformat()

    logger.info(
        "calendar_parser llm_request model=%s base_url=%s utterance=%r",
        model,
        base_url,
        utterance.encode("cp1252", errors="replace").decode("cp1252"),
    )

    payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": [
                    {"type": "input_text", "text": _prompt()},
                    {"type": "input_text", "text": f"Current local datetime for interpretation: {local_now}"},
                ],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": utterance}],
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "calendar_user_action",
                "schema": _ACTION_SCHEMA,
                "strict": True,
            }
        },
        "temperature": 0,
    }
    responses_data: dict | None = None
    completions_data: dict | None = None
    responses_error: Exception | None = None
    content_text = ""

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0, read=30.0, write=10.0, pool=5.0)) as client:
        if provider == "openai":
            try:
                resp = await client.post(f"{base_url}/responses", headers=headers, json=payload)
                resp.raise_for_status()
                responses_data = resp.json()
                logger.info("calendar_parser llm_response received status=%s", resp.status_code)
                content_text = extract_output_text_from_responses_payload(
                    responses_data,
                    missing_message="responses output_text missing for calendar parser",
                )
            except Exception as exc:
                responses_error = exc

        if not content_text:
            completions_payload = {
                "model": model,
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "system",
                        "content": _prompt() + "\nCurrent local datetime for interpretation: " + local_now,
                    },
                    {"role": "user", "content": utterance},
                ],
                "temperature": 0,
            }
            resp = await client.post(f"{base_url}/chat/completions", headers=headers, json=completions_payload)
            resp.raise_for_status()
            completions_data = resp.json()
            logger.info("calendar_parser llm_chat_completion_status=%s", resp.status_code)
            content_text = extract_output_text_from_chat_payload(completions_data)

    parsed = _parse_model_payload(json.loads(content_text))
    usage_payload = responses_data if responses_data is not None and responses_error is None else completions_data
    parsed.usage = extract_llm_usage(usage_payload or {}, prompt_text=utterance, completion_text=content_text)
    if responses_error is not None:
        parsed.reasoning = f"{parsed.reasoning}; responses_fallback={type(responses_error).__name__}"

    logger.info(
        "calendar_parser llm_output action=%s desired_start_at=%s duration_minutes=%s attendees=%s reasoning=%s",
        parsed.action,
        parsed.desired_start_at,
        parsed.duration_minutes,
        [_safe_log_text(item) for item in parsed.attendee_queries],
        _safe_log_text(parsed.reasoning),
    )
    return parsed


async def parse_calendar_user_action(db: AsyncSession, utterance: str) -> ParsedCalendarAction:
    config = await get_llm_config(db)
    try:
        return await asyncio.wait_for(_llm_parse_calendar_user_action(utterance, config), timeout=35.0)
    except Exception as exc:
        if not _CALENDAR_CANDIDATE_RE.search(utterance or ""):
            return ParsedCalendarAction(
                action="none",
                title="",
                attendee_queries=[],
                desired_start_at=None,
                duration_minutes=None,
                reasoning=f"fallback:not_calendar_candidate:{type(exc).__name__}",
            )
        raise