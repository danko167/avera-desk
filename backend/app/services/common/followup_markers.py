from __future__ import annotations

import re


FOLLOW_UP_MARKER_RE = re.compile(r"\[fu:([a-zA-Z0-9\-]+)\]")


def extract_follow_up_id(message: str) -> str | None:
    match = FOLLOW_UP_MARKER_RE.search(message or "")
    if not match:
        return None
    return match.group(1)


def strip_follow_up_marker(message: str) -> str:
    text = FOLLOW_UP_MARKER_RE.sub("", message or "")
    return " ".join(text.split()).strip()
