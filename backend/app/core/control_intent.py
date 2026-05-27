from __future__ import annotations

import re
from typing import Literal


ControlIntentKind = Literal[
    "send_control",
    "cancel_control",
    "dismiss_control",
    "affirmative_short",
    "other",
    "empty",
]


_SEND_CONTROL_RE = re.compile(
    r"\b(send|send\s+it|send\s+now|confirm|approve|yes\s+send|s\s+and\s+it|say\s+end\s+it|sand\s+it)\b",
    re.IGNORECASE,
)
_CANCEL_CONTROL_RE = re.compile(
    r"\b(cancel|discard|don't\s+send|do\s+not\s+send|never\s*mind|forget\s*it)\b",
    re.IGNORECASE,
)
_DISMISS_CONTROL_RE = re.compile(
    r"\b(dismiss|dismissed|ignore\s+this|close\s+this|mark\s+as\s+done|mark\s+done)\b",
    re.IGNORECASE,
)
_AFFIRMATIVE_RE = re.compile(
    r"^\s*(?:oh\s*,?\s*)?(?:yes|yeah|yep|sure|ok(?:ay)?|sounds\s+good|works\s+for\s+me|that\s+works|confirmed|i\s+can\s+do\s+that|we\s+can\s+do\s+that)\b",
    re.IGNORECASE,
)
_COMMAND_CUE_RE = re.compile(
    r"\b(cancel|discard|don't\s+send|do\s+not\s+send|never\s*mind|forget\s*it|dismiss|dismissed|ignore\s+this|close\s+this|mark\s+as\s+done|mark\s+done|send|send\s+it|send\s+now|confirm|approve|yes\s+send|s\s+and\s+it|say\s+end\s+it|sand\s+it)\b",
    re.IGNORECASE,
)
_NOISE_PREFIX_MAX_TOKENS = 3
_NOISE_PREFIX_TOKENS = {
    "a",
    "ah",
    "an",
    "end",
    "erm",
    "for",
    "hey",
    "hmm",
    "oh",
    "the",
    "uh",
    "um",
    "you",
}


def normalize_control_utterance(text: str) -> str:
    lowered = (text or "").strip().lower()
    if not lowered:
        return ""
    normalized = re.sub(r"[^a-z0-9'\s]", " ", lowered)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def classify_control_intent(text: str) -> tuple[ControlIntentKind, str]:
    normalized = normalize_control_utterance(text)
    if not normalized:
        return "empty", normalized
    if _CANCEL_CONTROL_RE.search(normalized):
        return "cancel_control", normalized
    if _DISMISS_CONTROL_RE.search(normalized):
        return "dismiss_control", normalized
    if _SEND_CONTROL_RE.search(normalized):
        return "send_control", normalized
    if _AFFIRMATIVE_RE.search(normalized):
        return "affirmative_short", normalized
    return "other", normalized


def trim_stt_noise_prefix(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""

    match = _COMMAND_CUE_RE.search(raw)
    if match is None or match.start() <= 0:
        return raw

    prefix = raw[: match.start()].strip()
    if not prefix:
        return raw

    prefix_token_count = len(re.findall(r"[A-Za-z0-9']+", prefix))
    if prefix_token_count == 0 or prefix_token_count > _NOISE_PREFIX_MAX_TOKENS:
        return raw

    prefix_tokens = [token for token in re.findall(r"[A-Za-z0-9']+", prefix.lower()) if token]
    if not prefix_tokens or not all(token in _NOISE_PREFIX_TOKENS for token in prefix_tokens):
        return raw

    trimmed = raw[match.start() :].lstrip(" \t\n\r\"'`.,!?;:-")
    return trimmed or raw
