from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import logging
import re
import unicodedata

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.runtime_config import get_llm_config
from ...prompts.loader import load_prompt
from ..ai.response_parsing import extract_output_text_from_chat_payload, extract_output_text_from_responses_payload
from .context import PreprocessedEmailContext
from ..ai.usage import LlmUsage, extract_llm_usage
from ..http_headers import build_json_headers

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
_REPLY_RE = re.compile(r"\b(reply|respond)\b", re.IGNORECASE)
_NEW_EMAIL_RE = re.compile(r"\b(write|send|compose|draft)\b.*\b(email|mail)\b", re.IGNORECASE)
_CALENDAR_INTENT_RE = re.compile(
    r"\b(meeting|calendar|invite|appointment|schedule|reschedule|tomorrow|today|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    re.IGNORECASE,
)
_RECIPIENT_CLAUSE_RE = re.compile(
    r"\b(?:email|mail)\s+to\s+(?P<recipient>.+?)(?:\s+\b(?:that|about|saying|regarding|re|subject)\b|$)",
    re.IGNORECASE,
)


@dataclass(slots=True)
class ParsedEmailAction:
    action: str  # none | reply | new_email
    recipient: str | None
    subject_hint: str | None
    message_instructions: str
    reasoning: str
    usage: LlmUsage | None = None


class EmailActionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str = Field(pattern="^(none|reply|new_email)$")
    recipient: str | None = None
    subject_hint: str | None = Field(default=None, max_length=180)
    message_instructions: str = Field(max_length=280)
    reasoning: str = Field(max_length=240)


_DEFAULT_PROMPT = """You interpret a user utterance into an outbound email action.
Return ONLY strict JSON with keys:
- action: one of \"none\", \"reply\", \"new_email\"
- recipient: email string or null
- subject_hint: short string or null
- message_instructions: concise text describing what email should say
- reasoning: short string
Rules:
- Choose action=reply when user asks to reply/respond to the current email context.
- Choose action=new_email when user asks to write/send a new email.
- Choose action=none if no outbound email is requested.
- Keep message_instructions compact and factual.
"""

_PROMPT_NAME = "email_user_action_system.v1.md"

_ACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["action", "recipient", "subject_hint", "message_instructions", "reasoning"],
    "properties": {
        "action": {"type": "string", "enum": ["none", "reply", "new_email"]},
        "recipient": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "subject_hint": {"anyOf": [{"type": "string", "maxLength": 180}, {"type": "null"}]},
        "message_instructions": {"type": "string", "maxLength": 280},
        "reasoning": {"type": "string", "maxLength": 240},
    },
}


def _prompt() -> str:
    return load_prompt(_PROMPT_NAME, default_text=_DEFAULT_PROMPT)


def _extract_email(text: str) -> str | None:
    match = _EMAIL_RE.search(text or "")
    if not match:
        spoken = _normalize_spoken_email_text(text or "")
        match = _EMAIL_RE.search(spoken)
        if not match:
            return None
    return match.group(0).strip().lower()


def _normalize_spoken_email_text(text: str) -> str:
    lowered = (text or "").strip().lower()
    ascii_folded = unicodedata.normalize("NFKD", lowered)
    ascii_folded = "".join(ch for ch in ascii_folded if not unicodedata.combining(ch))

    normalized = re.sub(r"[,:;!?()\[\]{}<>\"']", " ", ascii_folded)
    normalized = re.sub(r"\s+(?:at|zavinac)\s+", "@", normalized)
    normalized = re.sub(r"\s+(?:dot|tecka|point)\s+", ".", normalized)
    normalized = re.sub(r"\s+(?:dash|hyphen|minus)\s+", "-", normalized)
    normalized = re.sub(r"\s+(?:underscore|podtrzitko)\s+", "_", normalized)
    # ASR often returns symbolic email separators with surrounding spaces.
    normalized = re.sub(r"\s*@\s*", "@", normalized)
    normalized = re.sub(r"\s*\.\s*", ".", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def extract_recipient_from_text(text: str) -> str | None:
    return _extract_email(text)


def _extract_named_recipient(text: str) -> str | None:
    match = _RECIPIENT_CLAUSE_RE.search(text or "")
    if not match:
        return None

    candidate = re.sub(r"\s+", " ", match.group("recipient")).strip(" ,.;:-")
    if not candidate:
        return None
    return candidate


def _heuristic_parse(utterance: str) -> ParsedEmailAction | None:
    text = (utterance or "").strip()
    if not text:
        return ParsedEmailAction(
            action="none",
            recipient=None,
            subject_hint=None,
            message_instructions="",
            reasoning="heuristic:empty",
        )

    if _CALENDAR_INTENT_RE.search(text) and not (
        _REPLY_RE.search(text)
        or _NEW_EMAIL_RE.search(text)
        or _EMAIL_RE.search(text)
        or _RECIPIENT_CLAUSE_RE.search(text)
    ):
        return ParsedEmailAction(
            action="none",
            recipient=None,
            subject_hint=None,
            message_instructions="",
            reasoning="heuristic:calendar_intent_not_email",
        )

    if _REPLY_RE.search(text):
        cleaned = re.sub(r"^(?:please\s+)?(?:reply|respond)(?:\s+(?:to|that))?\s*", "", text, flags=re.IGNORECASE)
        instructions = cleaned.strip() or text
        return ParsedEmailAction(
            action="reply",
            recipient=None,
            subject_hint=None,
            message_instructions=instructions,
            reasoning="heuristic:reply_keyword",
        )

    if _NEW_EMAIL_RE.search(text):
        recipient = _extract_email(text) or _extract_named_recipient(text)
        instructions = text
        return ParsedEmailAction(
            action="new_email",
            recipient=recipient,
            subject_hint=None,
            message_instructions=instructions,
            reasoning="heuristic:new_email_keyword",
        )

    return None


def _parse_model_payload(payload: object) -> ParsedEmailAction:
    try:
        validated = EmailActionPayload.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"email action payload validation failed: {exc}") from exc

    recipient = (validated.recipient or "").strip() or None
    subject_hint = (validated.subject_hint or "").strip() or None
    instructions = validated.message_instructions.strip()

    if validated.action == "new_email" and recipient is None:
        # New email can still proceed if downstream context provides recipient.
        pass

    if validated.action == "none":
        instructions = ""

    return ParsedEmailAction(
        action=validated.action,
        recipient=recipient,
        subject_hint=subject_hint,
        message_instructions=instructions,
        reasoning=f"llm:{validated.reasoning.strip() or 'ok'}",
    )


async def _llm_parse(
    utterance: str,
    context: PreprocessedEmailContext,
    config,
) -> ParsedEmailAction:
    model = config.model or "gpt-5.4-mini"
    base_url = config.base_url.rstrip("/")
    headers = build_json_headers(config.api_key)
    provider = (config.provider or "").lower()

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
                    {
                        "type": "input_text",
                        "text": "Compact context:\n" + context.to_prompt_block(),
                    },
                    {"type": "input_text", "text": "User utterance:\n" + utterance},
                ],
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "email_user_action",
                "schema": _ACTION_SCHEMA,
                "strict": True,
            }
        },
        "temperature": 0,
    }
    user_prompt = "Compact context:\n" + context.to_prompt_block() + "\n\nUser utterance:\n" + utterance

    content_text = ""
    responses_data: dict | None = None
    completions_data: dict | None = None
    responses_error: Exception | None = None

    async with httpx.AsyncClient(timeout=httpx.Timeout(25.0, connect=5.0, read=25.0, write=10.0, pool=5.0)) as client:
        if provider == "openai":
            try:
                resp = await client.post(f"{base_url}/responses", headers=headers, json=payload)
                resp.raise_for_status()
                responses_data = resp.json()
                content_text = extract_output_text_from_responses_payload(
                    responses_data,
                    missing_message="responses output_text missing for email action parser",
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


async def parse_email_user_action(
    db: AsyncSession,
    *,
    utterance: str,
    context: PreprocessedEmailContext,
) -> ParsedEmailAction:
    config = await get_llm_config(db)
    logger.info(
        "email_action_parser llm_fallback utterance=%r",
        utterance.encode("cp1252", errors="replace").decode("cp1252"),
    )
    try:
        return await asyncio.wait_for(_llm_parse(utterance, context, config), timeout=30.0)
    except Exception as exc:
        logger.warning("email_action_parser failed, using heuristic fallback error=%s", exc)
        heuristic = _heuristic_parse(utterance)
        if heuristic is not None:
            return heuristic
        return ParsedEmailAction(
            action="none",
            recipient=None,
            subject_hint=None,
            message_instructions="",
            reasoning=f"fallback:none:{type(exc).__name__}",
        )
