from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
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

_CALENDAR_HINT_RE = re.compile(r"\b(meeting|calendar|schedule|reschedule|appointment|invite|call|event|tomorrow|today|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.IGNORECASE)
_EMAIL_HINT_RE = re.compile(r"\b(email|mail|reply|respond|forward|subject|draft)\b", re.IGNORECASE)
_SEND_DRAFT_RE = re.compile(r"\b(send|send it|confirm|approve|yes send)\b", re.IGNORECASE)
_CANCEL_DRAFT_RE = re.compile(r"\b(cancel|cancel draft|discard|don't send|do not send)\b", re.IGNORECASE)
_MODIFY_DRAFT_RE = re.compile(r"\b(change|update|edit)\b.*\b(recipient|subject|body|draft)\b", re.IGNORECASE)
_TIME_HINT_RE = re.compile(r"\b(today|tomorrow|tonight|monday|tuesday|wednesday|thursday|friday|saturday|sunday|\d{1,2}(?::\d{2})?\s*(am|pm)?)\b", re.IGNORECASE)
_SPOKEN_TIME_HINT_RE = re.compile(
    r"\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s*(am|pm)\b|\b(noon|midnight)\b",
    re.IGNORECASE,
)


@dataclass(slots=True)
class ParsedSpeechIntent:
    domain: str  # email | calendar | none
    action: str  # compose | modify_draft | send_draft | cancel_draft | create_event | update_event | cancel_event | none
    slots: dict[str, Any]
    confidence: float
    missing_slots: list[str]
    clarification_question: str | None
    reasoning: str
    usage: LlmUsage | None = None


class SpeechIntentPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain: str = Field(pattern="^(email|calendar|none)$")
    action: str = Field(pattern="^(compose|modify_draft|send_draft|cancel_draft|create_event|update_event|cancel_event|none)$")
    slots: dict = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)
    missing_slots: list[str] = Field(default_factory=list, max_length=8)
    clarification_question: str | None = Field(default=None, max_length=220)
    reasoning: str = Field(max_length=240)


_DEFAULT_PROMPT = """You are Stage A intent routing for spoken assistant commands.
Return ONLY strict JSON with keys:
- domain: one of "email", "calendar", "none"
- action: one of "compose", "modify_draft", "send_draft", "cancel_draft", "create_event", "update_event", "cancel_event", "none"
- slots: object with optional extracted hints (e.g. compose_mode, target_event_phrase)
- confidence: number from 0 to 1
- missing_slots: array of missing required slots for the chosen intent
- clarification_question: short follow-up question when missing_slots is not empty, otherwise null
- reasoning: short string

Rules:
- Keep draft operations inside domain=email with actions send_draft/cancel_draft/modify_draft.
- Use domain=calendar + action=create_event for new scheduling requests.
- Use domain=calendar + action=update_event for move/reschedule adjustments.
- Use domain=calendar + action=cancel_event for delete/remove/cancel event requests.
- Use domain=email + action=compose for new/reply/forward email writing.
- Use domain=none + action=none for unrelated/unclear requests.
- If calendar action needs a date/time and missing it, include missing_slots with "desired_start_at" and set clarification_question.
- If draft action is requested but no active draft exists, include missing_slots with "active_draft".

Negative examples (do not misroute):
- "make a meeting with Danko tomorrow at 2" -> domain=calendar action=create_event (NOT email)
- "reply to this email" -> domain=email action=compose (NOT calendar)
- "send it" with active draft -> domain=email action=send_draft
"""

_PROMPT_NAME = "speech_intent_router_system.v1.md"

_INTENT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["domain", "action", "slots", "confidence", "missing_slots", "clarification_question", "reasoning"],
    "properties": {
        "domain": {"type": "string", "enum": ["email", "calendar", "none"]},
        "action": {
            "type": "string",
            "enum": [
                "compose",
                "modify_draft",
                "send_draft",
                "cancel_draft",
                "create_event",
                "update_event",
                "cancel_event",
                "none",
            ],
        },
        "slots": {"type": "object", "additionalProperties": True},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "missing_slots": {
            "type": "array",
            "items": {"type": "string", "maxLength": 64},
            "maxItems": 8,
        },
        "clarification_question": {"anyOf": [{"type": "string", "maxLength": 220}, {"type": "null"}]},
        "reasoning": {"type": "string", "maxLength": 240},
    },
}


def _prompt() -> str:
    return load_prompt(_PROMPT_NAME, default_text=_DEFAULT_PROMPT)


def _parse_model_payload(payload: object) -> ParsedSpeechIntent:
    try:
        validated = SpeechIntentPayload.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"speech intent payload validation failed: {exc}") from exc

    missing_slots = [slot.strip() for slot in validated.missing_slots if slot and slot.strip()]
    clarification_question = (validated.clarification_question or "").strip() or None
    if missing_slots and clarification_question is None:
        clarification_question = "Could you clarify that request in one short sentence?"

    return ParsedSpeechIntent(
        domain=validated.domain,
        action=validated.action,
        slots=dict(validated.slots or {}),
        confidence=float(validated.confidence),
        missing_slots=missing_slots,
        clarification_question=clarification_question,
        reasoning=f"llm:{validated.reasoning.strip() or 'ok'}",
    )


def _has_explicit_time_hint(text: str) -> bool:
    candidate = (text or "").strip().lower()
    return bool(_TIME_HINT_RE.search(candidate) or _SPOKEN_TIME_HINT_RE.search(candidate))


def _stabilize_calendar_missing_slots(parsed: ParsedSpeechIntent, *, utterance: str) -> ParsedSpeechIntent:
    if parsed.domain != "calendar" or parsed.action != "create_event":
        return parsed
    if "desired_start_at" not in parsed.missing_slots:
        return parsed

    text = (utterance or "").strip()
    if not _CALENDAR_HINT_RE.search(text):
        return parsed
    if not _has_explicit_time_hint(text):
        return parsed

    parsed.missing_slots = [slot for slot in parsed.missing_slots if slot != "desired_start_at"]
    if not parsed.missing_slots:
        parsed.clarification_question = None
    parsed.reasoning = f"{parsed.reasoning};calendar_time_rescue"
    return parsed


async def _llm_route_intent(
    *,
    utterance: str,
    has_active_draft: bool,
    notification_id: str | None,
    config,
) -> ParsedSpeechIntent:
    model = config.model or "gpt-5.4-mini"
    base_url = config.base_url.rstrip("/")
    headers = build_json_headers(config.api_key)
    provider = (config.provider or "").lower()

    context_block = (
        f"has_active_draft={has_active_draft}\n"
        f"notification_id_present={bool(notification_id)}"
    )

    payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": _prompt()}],
            },
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Context:\n" + context_block},
                    {"type": "input_text", "text": "User utterance:\n" + utterance},
                ],
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "speech_intent_router",
                "schema": _INTENT_SCHEMA,
                "strict": True,
            }
        },
        "temperature": 0,
    }

    user_prompt = "Context:\n" + context_block + "\n\nUser utterance:\n" + utterance
    responses_data: dict | None = None
    completions_data: dict | None = None
    responses_error: Exception | None = None
    content_text = ""

    async with httpx.AsyncClient(timeout=httpx.Timeout(25.0, connect=5.0, read=25.0, write=10.0, pool=5.0)) as client:
        if provider == "openai":
            try:
                resp = await client.post(f"{base_url}/responses", headers=headers, json=payload)
                resp.raise_for_status()
                responses_data = resp.json()
                content_text = extract_output_text_from_responses_payload(
                    responses_data,
                    missing_message="responses output_text missing for speech intent router",
                )
            except Exception as exc:
                responses_error = exc

        if not content_text:
            completions_payload = {
                "model": model,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": _prompt()},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0,
            }
            resp = await client.post(f"{base_url}/chat/completions", headers=headers, json=completions_payload)
            resp.raise_for_status()
            completions_data = resp.json()
            content_text = extract_output_text_from_chat_payload(completions_data)

    parsed = _parse_model_payload(json.loads(content_text))
    usage_payload = responses_data if responses_data is not None and responses_error is None else completions_data
    parsed.usage = extract_llm_usage(usage_payload or {}, prompt_text=utterance, completion_text=content_text)
    if responses_error is not None:
        parsed.reasoning = f"{parsed.reasoning}; responses_fallback={type(responses_error).__name__}"
    return parsed


def _heuristic_route_intent(
    *,
    utterance: str,
    has_active_draft: bool,
) -> ParsedSpeechIntent:
    text = (utterance or "").strip()
    lowered = text.lower()
    if not lowered:
        return ParsedSpeechIntent(
            domain="none",
            action="none",
            slots={},
            confidence=0.2,
            missing_slots=[],
            clarification_question=None,
            reasoning="heuristic:empty",
        )

    if _SEND_DRAFT_RE.search(text):
        missing_slots = [] if has_active_draft else ["active_draft"]
        question = None if has_active_draft else "There is no active draft. Say 'write an email' first."
        return ParsedSpeechIntent(
            domain="email",
            action="send_draft",
            slots={},
            confidence=0.88,
            missing_slots=missing_slots,
            clarification_question=question,
            reasoning="heuristic:send_draft",
        )
    if _CANCEL_DRAFT_RE.search(text):
        missing_slots = [] if has_active_draft else ["active_draft"]
        question = None if has_active_draft else "There is no active draft to cancel."
        return ParsedSpeechIntent(
            domain="email",
            action="cancel_draft",
            slots={},
            confidence=0.86,
            missing_slots=missing_slots,
            clarification_question=question,
            reasoning="heuristic:cancel_draft",
        )
    if _MODIFY_DRAFT_RE.search(text):
        missing_slots = [] if has_active_draft else ["active_draft"]
        question = None if has_active_draft else "There is no active draft to edit."
        return ParsedSpeechIntent(
            domain="email",
            action="modify_draft",
            slots={},
            confidence=0.84,
            missing_slots=missing_slots,
            clarification_question=question,
            reasoning="heuristic:modify_draft",
        )

    if _CALENDAR_HINT_RE.search(text):
        missing_slots: list[str] = []
        question: str | None = None
        if not _has_explicit_time_hint(lowered):
            missing_slots = ["desired_start_at"]
            question = "What date and time should I schedule it for?"
        return ParsedSpeechIntent(
            domain="calendar",
            action="create_event",
            slots={},
            confidence=0.78,
            missing_slots=missing_slots,
            clarification_question=question,
            reasoning="heuristic:calendar",
        )
    if _EMAIL_HINT_RE.search(text):
        return ParsedSpeechIntent(
            domain="email",
            action="compose",
            slots={},
            confidence=0.75,
            missing_slots=[],
            clarification_question=None,
            reasoning="heuristic:email",
        )

    return ParsedSpeechIntent(
        domain="none",
        action="none",
        slots={},
        confidence=0.35,
        missing_slots=[],
        clarification_question="Could you rephrase that as an email or calendar action?",
        reasoning="heuristic:unknown",
    )


async def route_speech_intent(
    db: AsyncSession,
    *,
    utterance: str,
    has_active_draft: bool,
    notification_id: str | None,
) -> ParsedSpeechIntent:
    config = await get_llm_config(db)
    try:
        parsed = await asyncio.wait_for(
            _llm_route_intent(
                utterance=utterance,
                has_active_draft=has_active_draft,
                notification_id=notification_id,
                config=config,
            ),
            timeout=25.0,
        )
        return _stabilize_calendar_missing_slots(parsed, utterance=utterance)
    except Exception as exc:
        logger.warning("speech_intent_router failed, using heuristic fallback error=%s", exc)
        return _heuristic_route_intent(
            utterance=utterance,
            has_active_draft=has_active_draft,
        )
