from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .models import SemanticGoal

RouteFn = Callable[..., Awaitable[Any]]


async def parse_goal(
    db: AsyncSession,
    *,
    utterance: str,
    notification_id: str | None,
    has_active_draft: bool,
    route_intent: RouteFn,
) -> SemanticGoal:
    parsed = await route_intent(
        db,
        utterance=utterance,
        has_active_draft=has_active_draft,
        notification_id=notification_id,
    )

    return SemanticGoal(
        utterance=utterance,
        domain=str(getattr(parsed, "domain", "none") or "none"),
        action=str(getattr(parsed, "action", "none") or "none"),
        slots=dict(getattr(parsed, "slots", {}) or {}),
        confidence=float(getattr(parsed, "confidence", 0.0) or 0.0),
        missing_slots=list(getattr(parsed, "missing_slots", []) or []),
        clarification_question=getattr(parsed, "clarification_question", None),
        reasoning=str(getattr(parsed, "reasoning", "") or ""),
        usage=getattr(parsed, "usage", None),
    )
