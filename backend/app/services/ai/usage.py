from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(slots=True)
class LlmUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


def _approx_tokens(text: str | None) -> int:
    normalized = (text or "").strip()
    if not normalized:
        return 0
    # Rough heuristic: 1 token ~= 4 chars in English-like text.
    return max(1, math.ceil(len(normalized) / 4))


def extract_llm_usage(payload: dict, *, prompt_text: str | None = None, completion_text: str | None = None) -> LlmUsage:
    usage = payload.get("usage") if isinstance(payload, dict) else None
    if isinstance(usage, dict):
        prompt_tokens = int(
            usage.get("input_tokens")
            or usage.get("prompt_tokens")
            or usage.get("input_token_count")
            or 0
        )
        completion_tokens = int(
            usage.get("output_tokens")
            or usage.get("completion_tokens")
            or usage.get("output_token_count")
            or 0
        )
        total_tokens = int(usage.get("total_tokens") or 0)

        if total_tokens <= 0:
            total_tokens = prompt_tokens + completion_tokens

        if prompt_tokens <= 0 and prompt_text is not None:
            prompt_tokens = _approx_tokens(prompt_text)
        if completion_tokens <= 0 and completion_text is not None:
            completion_tokens = _approx_tokens(completion_text)
        if total_tokens <= 0:
            total_tokens = prompt_tokens + completion_tokens

        return LlmUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )

    prompt_tokens = _approx_tokens(prompt_text)
    completion_tokens = _approx_tokens(completion_text)
    return LlmUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
    )
