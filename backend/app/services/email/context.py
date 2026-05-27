from __future__ import annotations

from dataclasses import dataclass
import re


_WHITESPACE_RE = re.compile(r"\s+")
_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_REPLY_HEADER_RE = re.compile(r"\b(?:from|sent|to|subject):\b", re.IGNORECASE)


def _compact_text(text: str, *, max_chars: int) -> str:
    normalized = _WHITESPACE_RE.sub(" ", (text or "").strip())
    normalized = _URL_RE.sub("<url>", normalized)
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 1].rstrip() + "..."


def _trim_reply_headers(text: str) -> str:
    if not text:
        return ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    filtered: list[str] = []
    for line in lines:
        if _REPLY_HEADER_RE.search(line):
            continue
        filtered.append(line)
    return "\n".join(filtered)


@dataclass(slots=True)
class PreprocessedEmailContext:
    message_id: str | None
    conversation_id: str | None
    from_address: str | None
    subject: str
    body_preview: str
    user_utterance: str

    def to_prompt_block(self) -> str:
        return "\n".join(
            [
                f"message_id={self.message_id or ''}",
                f"conversation_id={self.conversation_id or ''}",
                f"from_address={self.from_address or ''}",
                f"subject={self.subject}",
                f"body_preview={self.body_preview}",
                f"user_utterance={self.user_utterance}",
            ]
        )


@dataclass(slots=True)
class PreprocessedIncomingEmailContext:
    subject: str
    body_preview: str

    def to_prompt_block(self) -> str:
        return "\n".join(
            [
                f"subject={self.subject}",
                f"body_preview={self.body_preview}",
            ]
        )


def preprocess_email_context(
    *,
    message_id: str | None,
    conversation_id: str | None,
    from_address: str | None,
    subject: str | None,
    body_preview: str | None,
    user_utterance: str,
) -> PreprocessedEmailContext:
    compact_subject = _compact_text(subject or "", max_chars=140)
    compact_preview = _compact_text(_trim_reply_headers(body_preview or ""), max_chars=520)
    compact_utterance = _compact_text(user_utterance, max_chars=240)

    return PreprocessedEmailContext(
        message_id=(message_id or "").strip() or None,
        conversation_id=(conversation_id or "").strip() or None,
        from_address=_compact_text(from_address or "", max_chars=160) or None,
        subject=compact_subject,
        body_preview=compact_preview,
        user_utterance=compact_utterance,
    )


def preprocess_incoming_email_context(
    *,
    subject: str | None,
    body_preview: str | None,
) -> PreprocessedIncomingEmailContext:
    return PreprocessedIncomingEmailContext(
        subject=_compact_text(subject or "", max_chars=140),
        body_preview=_compact_text(_trim_reply_headers(body_preview or ""), max_chars=520),
    )
