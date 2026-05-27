"""Shared prompt loading utilities for markdown prompt files."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parent


def _normalize_prompt_filename(name: str) -> str:
    normalized = (name or "").strip()
    if not normalized:
        raise ValueError("Prompt name must be non-empty")

    if not normalized.endswith(".md"):
        normalized = f"{normalized}.md"

    return normalized


@lru_cache(maxsize=128)
def load_prompt(name: str, default_text: str = "") -> str:
    """Load a markdown prompt by filename from app/prompts.

    Example names:
    - "follow_up_extractor_system.v1.md"
    - "reply_draft_system.v1" (extension is added automatically)
    """
    filename = _normalize_prompt_filename(name)
    prompt_path = _PROMPTS_DIR / filename

    try:
        text = prompt_path.read_text(encoding="utf-8").strip()
        if text:
            return text
    except OSError:
        pass

    return default_text.strip()
