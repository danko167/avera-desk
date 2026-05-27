from __future__ import annotations

from .models import SemanticGoal


DEFAULT_CLARIFICATION = "Could you provide a bit more detail so I can do that?"


CALENDAR_TIME_CLARIFICATION = (
    "I can schedule that, but I still need a date and time. "
    "For example: 'tomorrow at 9 AM' or 'Friday at 14:30'."
)


def resolve_clarification(goal: SemanticGoal) -> str:
    if (
        goal.domain == "calendar"
        and goal.action in {"create_event", "update_event"}
        and "desired_start_at" in goal.missing_slots
    ):
        return CALENDAR_TIME_CLARIFICATION

    return goal.clarification_question or DEFAULT_CLARIFICATION
