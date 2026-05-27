"""Parse natural-language follow-up actions from user utterances."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
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

_LOCAL_TIME_OVERRIDES: list[tuple[re.Pattern[str], int, time]] = [
    (re.compile(r"\btomorrow\s+morning\b", re.IGNORECASE), 1, time(hour=9, minute=0)),
    (re.compile(r"\btomorrow\s+(?:at\s+)?noon\b", re.IGNORECASE), 1, time(hour=12, minute=0)),
    (re.compile(r"\btomorrow\s+afternoon\b", re.IGNORECASE), 1, time(hour=15, minute=0)),
    (re.compile(r"\btomorrow\s+evening\b", re.IGNORECASE), 1, time(hour=19, minute=0)),
    (
        re.compile(
            r"\btomorrow\b(?!\s+(?:morning|(?:at\s+)?noon|afternoon|evening))",
            re.IGNORECASE,
        ),
        1,
        time(hour=9, minute=0),
    ),
    (re.compile(r"\btonight\b", re.IGNORECASE), 0, time(hour=20, minute=0)),
    (re.compile(r"\bthis\s+afternoon\b", re.IGNORECASE), 0, time(hour=15, minute=0)),
    (re.compile(r"\bthis\s+evening\b", re.IGNORECASE), 0, time(hour=19, minute=0)),
]


@dataclass(slots=True)
class ParsedFollowUpAction:
    action: str  # none | snooze | dismiss | complete
    snooze_minutes: int | None
    snooze_until: datetime | None
    reasoning: str
    usage: LlmUsage | None = None

    def resolve_snooze_at(self, *, now_utc: datetime | None = None) -> datetime | None:
        if self.action != "snooze":
            return None

        effective_now = now_utc or datetime.now(timezone.utc)
        if self.snooze_until is not None:
            if self.snooze_until.tzinfo is None:
                local_tz = datetime.now().astimezone().tzinfo
                target = self.snooze_until.replace(tzinfo=local_tz)
            else:
                target = self.snooze_until
            target_utc = target.astimezone(timezone.utc)
            if target_utc > effective_now:
                return target_utc

        minutes = self.snooze_minutes or (24 * 60)
        return effective_now + timedelta(minutes=minutes)


class FollowUpActionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str = Field(pattern="^(none|snooze|dismiss|complete)$")
    snooze_minutes: int | None = Field(default=None, ge=1, le=60 * 24 * 365)
    snooze_until: str | None = None
    reasoning: str = Field(max_length=240)


_DEFAULT_PROMPT = """You interpret user utterances about a currently active follow-up reminder.
Return ONLY strict JSON object with keys:
- action: one of \"none\", \"snooze\", \"dismiss\", \"complete\"
- snooze_minutes: integer or null
- snooze_until: ISO8601 datetime string with timezone offset, or null
- reasoning: short string
If the user asks to be reminded later, set action to \"snooze\".
Use snooze_minutes for simple durations like \"in 2 hours\" or \"in 10 minutes\".
Use snooze_until for calendar-like or anchored times like \"tomorrow morning\", \"tomorrow\", \"tonight\", or \"next Tuesday at 3pm\".
Provide exactly one of snooze_minutes or snooze_until for action=\"snooze\". Use null for both when action is not snooze.
Interpret relative times directly from natural language, including number words and seconds.
Convert seconds to minutes, rounding up to at least 1 minute when using snooze_minutes.
"""

_PROMPT_NAME = "follow_up_user_action_system.v1.md"

_ACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["action", "snooze_minutes", "snooze_until", "reasoning"],
    "properties": {
        "action": {"type": "string", "enum": ["none", "snooze", "dismiss", "complete"]},
        "snooze_minutes": {
            "anyOf": [
                {"type": "integer", "minimum": 1, "maximum": 60 * 24 * 365},
                {"type": "null"},
            ]
        },
        "snooze_until": {
            "anyOf": [
                {"type": "string"},
                {"type": "null"},
            ]
        },
        "reasoning": {"type": "string", "maxLength": 240},
    },
}


def _prompt() -> str:
    return load_prompt(_PROMPT_NAME, default_text=_DEFAULT_PROMPT)


def _parse_snooze_until(raw: str | None) -> datetime | None:
    if raw is None:
        return None

    candidate = raw.strip()
    if not candidate:
        return None

    normalized = candidate.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"invalid snooze_until datetime: {raw}") from exc


def _parse_model_payload(payload: object) -> ParsedFollowUpAction:
    try:
        validated = FollowUpActionPayload.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"action payload validation failed: {exc}") from exc

    snooze_until = _parse_snooze_until(validated.snooze_until)
    if validated.action == "snooze":
        provided_fields = int(validated.snooze_minutes is not None) + int(snooze_until is not None)
        if provided_fields != 1:
            raise ValueError("snooze action must provide exactly one of snooze_minutes or snooze_until")
    elif validated.snooze_minutes is not None or snooze_until is not None:
        raise ValueError("non-snooze action must not provide snooze_minutes or snooze_until")

    return ParsedFollowUpAction(
        action=validated.action,
        snooze_minutes=validated.snooze_minutes,
        snooze_until=snooze_until,
        reasoning=f"llm:{validated.reasoning.strip() or 'ok'}",
    )


def _local_target_datetime(now_local: datetime, day_offset: int, target_time: time) -> datetime:
    target_date = (now_local + timedelta(days=day_offset)).date()
    target_local = datetime.combine(target_date, target_time, tzinfo=now_local.tzinfo)
    if target_local <= now_local:
        target_local = target_local + timedelta(days=1)
    return target_local


def _apply_local_time_override(utterance: str, parsed: ParsedFollowUpAction) -> ParsedFollowUpAction:
    if parsed.action != "snooze":
        return parsed

    now_local = datetime.now().astimezone()
    for pattern, day_offset, target_time in _LOCAL_TIME_OVERRIDES:
        if not pattern.search(utterance):
            continue

        target_local = _local_target_datetime(now_local, day_offset, target_time)
        return ParsedFollowUpAction(
            action=parsed.action,
            snooze_minutes=None,
            snooze_until=target_local,
            reasoning=f"{parsed.reasoning}; local_override={pattern.pattern}",
        )

    return parsed


async def _parse_follow_up_user_action_via_llm(utterance: str, config) -> ParsedFollowUpAction:
    model = config.model or "gpt-5.4-mini"
    base_url = config.base_url.rstrip("/")
    headers = build_json_headers(config.api_key)
    provider = (config.provider or "").lower()
    local_now = datetime.now().astimezone().isoformat()

    logger.info(
        "follow_up_parser llm_request model=%s base_url=%s utterance=%r",
        model,
        base_url,
        utterance,
    )

    payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": [
                    {"type": "input_text", "text": _prompt()},
                    {
                        "type": "input_text",
                        "text": f"Current local datetime for interpretation: {local_now}",
                    },
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
                "name": "follow_up_user_action",
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
                logger.info("follow_up_parser llm_response received status=%s", resp.status_code)
                content_text = extract_output_text_from_responses_payload(responses_data)
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
            logger.info("follow_up_parser llm_chat_completion_status=%s", resp.status_code)
            content_text = extract_output_text_from_chat_payload(completions_data)

    parsed = _parse_model_payload(json.loads(content_text))
    usage_payload = responses_data if responses_data is not None and responses_error is None else completions_data
    parsed.usage = extract_llm_usage(usage_payload or {}, prompt_text=utterance, completion_text=content_text)
    if responses_error is not None:
        parsed.reasoning = f"{parsed.reasoning}; responses_fallback={type(responses_error).__name__}"

    logger.info(
        "follow_up_parser llm_output action=%s snooze_minutes=%s snooze_until=%s reasoning=%s",
        parsed.action,
        parsed.snooze_minutes,
        parsed.snooze_until,
        parsed.reasoning,
    )
    return parsed


async def parse_follow_up_user_action(db: AsyncSession, utterance: str) -> ParsedFollowUpAction:
    config = await get_llm_config(db)
    parsed = await asyncio.wait_for(_parse_follow_up_user_action_via_llm(utterance, config), timeout=35.0)
    return _apply_local_time_override(utterance, parsed)
