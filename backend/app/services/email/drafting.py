from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import re

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.runtime_config import get_llm_config
from ...integrations.m365 import oauth
from ...prompts.loader import load_prompt
from ..ai.response_parsing import extract_output_text_from_chat_payload, extract_output_text_from_responses_payload
from .context import PreprocessedEmailContext
from ..ai.usage import LlmUsage, extract_llm_usage
from ..http_headers import build_json_headers


@dataclass(slots=True)
class DraftedEmail:
    subject: str
    body: str
    tone: str
    confidence: float
    reasoning: str
    usage: LlmUsage | None = None


class DraftPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str = Field(max_length=180)
    body: str = Field(max_length=2400)
    tone: str = Field(max_length=80)
    confidence: float = Field(ge=0, le=1)
    reasoning: str = Field(max_length=240)


_DEFAULT_PROMPT = """You draft concise, professional emails.
Return ONLY strict JSON object with keys:
- subject: string
- body: string
- tone: string
- confidence: number between 0 and 1
- reasoning: short string
Rules:
- Keep content directly relevant to the user request.
- Be polite and clear.
- Do not fabricate facts.
- If context is insufficient, include one short clarifying question in the draft body.
- Keep body under 220 words unless user explicitly asks longer.
"""

_PROMPT_NAME = "reply_draft_system.v1.md"

_DRAFT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["subject", "body", "tone", "confidence", "reasoning"],
    "properties": {
        "subject": {"type": "string", "maxLength": 180},
        "body": {"type": "string", "maxLength": 2400},
        "tone": {"type": "string", "maxLength": 80},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "reasoning": {"type": "string", "maxLength": 240},
    },
}


def _prompt() -> str:
    return load_prompt(_PROMPT_NAME, default_text=_DEFAULT_PROMPT)


_NAME_PLACEHOLDER_RE = re.compile(r"(?:\[|\{|<)\s*(?:your|my)\s+name\s*(?:\]|\}|>)", re.IGNORECASE)


def _derive_name_from_mailbox(mailbox: str | None) -> str | None:
    value = (mailbox or "").strip()
    if "@" not in value:
        return None
    local = value.split("@", 1)[0].strip()
    if not local:
        return None
    parts = [part for part in re.split(r"[._\-]+", local) if part]
    if not parts:
        return None
    return " ".join(part.capitalize() for part in parts)


def _apply_sender_name(body: str, sender_name: str | None) -> str:
    if not sender_name:
        return body
    return _NAME_PLACEHOLDER_RE.sub(sender_name, body)


def _parse_payload(payload: object, *, default_subject: str, sender_name: str | None) -> DraftedEmail:
    try:
        validated = DraftPayload.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"draft payload validation failed: {exc}") from exc

    subject = validated.subject.strip() or default_subject
    body = validated.body.strip()
    if not body:
        body = "Thanks for your email. I will get back to you shortly."
    body = _apply_sender_name(body, sender_name)

    return DraftedEmail(
        subject=subject,
        body=body,
        tone=validated.tone.strip() or "professional",
        confidence=max(0.0, min(1.0, float(validated.confidence))),
        reasoning=validated.reasoning.strip() or "llm",
    )


async def _llm_draft(
    *,
    context: PreprocessedEmailContext,
    user_instruction: str,
    mode: str,
    default_subject: str,
    sender_name: str | None,
    config,
) -> DraftedEmail:
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
                        "text": "Mode: " + mode,
                    },
                    {
                        "type": "input_text",
                        "text": "Default subject: " + default_subject,
                    },
                    {
                        "type": "input_text",
                        "text": "Sender display name: " + (sender_name or "unknown"),
                    },
                    {
                        "type": "input_text",
                        "text": "Compact context:\n" + context.to_prompt_block(),
                    },
                    {
                        "type": "input_text",
                        "text": "User instruction:\n" + user_instruction,
                    },
                ],
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "email_draft",
                "schema": _DRAFT_SCHEMA,
                "strict": True,
            }
        },
        "temperature": 0.2,
    }
    user_prompt = (
        "Mode: " + mode + "\n"
        "Default subject: " + default_subject + "\n"
        "Sender display name: " + (sender_name or "unknown") + "\n\n"
        "Compact context:\n" + context.to_prompt_block() + "\n\n"
        "User instruction:\n" + user_instruction
    )

    content_text = ""
    responses_data: dict | None = None
    completions_data: dict | None = None
    responses_error: Exception | None = None

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0, read=30.0, write=10.0, pool=5.0)) as client:
        if provider == "openai":
            try:
                resp = await client.post(f"{base_url}/responses", headers=headers, json=payload)
                resp.raise_for_status()
                responses_data = resp.json()
                content_text = extract_output_text_from_responses_payload(
                    responses_data,
                    missing_message="responses output_text missing for email draft",
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
                "temperature": 0.2,
            }
            resp = await client.post(f"{base_url}/chat/completions", headers=headers, json=completions_payload)
            resp.raise_for_status()
            completions_data = resp.json()
            content_text = extract_output_text_from_chat_payload(completions_data)

    drafted = _parse_payload(
        json.loads(content_text),
        default_subject=default_subject,
        sender_name=sender_name,
    )
    usage_payload = responses_data if responses_data is not None and responses_error is None else completions_data
    drafted.usage = extract_llm_usage(usage_payload or {}, prompt_text=user_instruction, completion_text=content_text)
    if responses_error is not None:
        drafted.reasoning = f"{drafted.reasoning}; responses_fallback={type(responses_error).__name__}"
    return drafted


async def draft_email(
    db: AsyncSession,
    *,
    context: PreprocessedEmailContext,
    user_instruction: str,
    mode: str,
    default_subject: str,
) -> DraftedEmail:
    config = await get_llm_config(db)
    sender_name = await oauth.get_authenticated_display_name(db)
    if not sender_name:
        mailbox = await oauth.get_authenticated_mailbox(db)
        sender_name = _derive_name_from_mailbox(mailbox)

    return await asyncio.wait_for(
        _llm_draft(
            context=context,
            user_instruction=user_instruction,
            mode=mode,
            default_subject=default_subject,
            sender_name=sender_name,
            config=config,
        ),
        timeout=35.0,
    )
