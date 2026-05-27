from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from app.core.control_intent import classify_control_intent

LATIN_TEXT_RE = re.compile(r"[A-Za-z]")
FOREIGN_PREFIX_RE = re.compile(r"^(?P<prefix>(?:[^\x00-\x7F]|\s|[?!.,;:'\"`~_\-]){1,24})(?P<rest>.*)$")
TRANSCRIPT_CONFIDENCE_MIN = 0.56


@dataclass(slots=True)
class SanitizedTranscriptResult:
    cleaned_text: str
    applied: bool
    prefix: str | None = None


def join_transcript_parts(existing: str, incoming: str) -> str:
    existing = existing.strip()
    incoming = incoming.strip()

    if not existing:
        return incoming
    if not incoming:
        return existing
    if incoming[0] in ",.!?;:":
        return f"{existing}{incoming}"
    return f"{existing} {incoming}"


def is_prompt_text(text: str) -> bool:
    normalized = text.strip().lower()
    return normalized in {
        "listening...",
        "listening for your command...",
    }


def sanitize_realtime_transcript_text(text: str) -> SanitizedTranscriptResult:
    raw = " ".join((text or "").strip().split())
    if not raw or not LATIN_TEXT_RE.search(raw):
        return SanitizedTranscriptResult(cleaned_text=raw, applied=False)

    match = FOREIGN_PREFIX_RE.match(raw)
    if not match:
        return SanitizedTranscriptResult(cleaned_text=raw, applied=False)

    prefix = match.group("prefix") or ""
    rest = (match.group("rest") or "").strip()
    if not rest or not LATIN_TEXT_RE.search(rest):
        return SanitizedTranscriptResult(cleaned_text=raw, applied=False)

    prefix_letters = [char for char in prefix if char.isalpha()]
    if not prefix_letters:
        return SanitizedTranscriptResult(cleaned_text=raw, applied=False)

    non_latin_prefix_letters = [
        char for char in prefix_letters if "LATIN" not in unicodedata.name(char, "")
    ]
    if len(non_latin_prefix_letters) < 2:
        return SanitizedTranscriptResult(cleaned_text=raw, applied=False)

    if len(prefix.strip()) <= 24:
        return SanitizedTranscriptResult(cleaned_text=rest, applied=True, prefix=prefix)

    return SanitizedTranscriptResult(cleaned_text=raw, applied=False)


def compute_transcript_confidence(
    *,
    text: str,
    event: dict | None,
    sanitization_applied: bool,
) -> float:
    normalized_text = " ".join((text or "").strip().split())
    words = [token for token in re.split(r"\s+", normalized_text) if token]

    direct_confidence = extract_direct_confidence(event)
    if direct_confidence is not None:
        confidence = direct_confidence
    else:
        confidence = 0.78
        if len(words) <= 2:
            confidence -= 0.20
        if len(normalized_text) < 12:
            confidence -= 0.12

        if words:
            unique_ratio = len(set(word.lower() for word in words)) / max(1, len(words))
            if unique_ratio < 0.45:
                confidence -= 0.15

        punctuation_count = len(re.findall(r"[^\w\s]", normalized_text))
        if punctuation_count >= 3:
            confidence -= 0.08

    # Preserve strictness overall, but allow explicit short control phrases that
    # users naturally say as a single word while confirming draft actions.
    control_kind, _ = classify_control_intent(normalized_text)
    if len(words) <= 3 and control_kind in {"send_control", "cancel_control", "dismiss_control"}:
        confidence += 0.14

    if sanitization_applied:
        confidence -= 0.06

    return max(0.0, min(0.99, confidence))


def extract_direct_confidence(event: dict | None) -> float | None:
    if not isinstance(event, dict):
        return None

    candidates = [
        event.get("confidence"),
        (event.get("transcription") or {}).get("confidence") if isinstance(event.get("transcription"), dict) else None,
        (event.get("metadata") or {}).get("confidence") if isinstance(event.get("metadata"), dict) else None,
    ]
    for candidate in candidates:
        if isinstance(candidate, (int, float)):
            value = float(candidate)
            if 0.0 <= value <= 1.0:
                return value
    return None


def should_request_clarification(confidence: float) -> bool:
    return confidence < TRANSCRIPT_CONFIDENCE_MIN


def clarification_prompt_for_text(text: str) -> str:
    cleaned = " ".join((text or "").strip().split())
    if not cleaned:
        return "I couldn't hear that clearly. Please repeat in one short sentence."
    return f'I heard "{cleaned}" but not clearly enough. Please repeat in one short sentence.'
