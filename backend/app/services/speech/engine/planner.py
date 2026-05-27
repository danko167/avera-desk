from __future__ import annotations

import re

from app.core.control_intent import classify_control_intent
from .models import ExecutionPlan, PlanStep, SemanticGoal, WorldState


_AFFIRMATIVE_RESPONSE_RE = re.compile(
    r"^\s*(?:oh\s*,?\s*)?(?:yes|yeah|yep|sure|ok(?:ay)?|sounds\s+good|works\s+for\s+me|that\s+works|confirmed|i\s+can\s+do\s+that|we\s+can\s+do\s+that)\b",
    re.IGNORECASE,
)
_NEGATIVE_RESPONSE_RE = re.compile(
    r"^\s*(?:oh\s*,?\s*)?(?:no|nope|can(?:\s*not|'t)|cannot|not\s+now|doesn'?t\s+work|won'?t\s+work|decline)\b",
    re.IGNORECASE,
)
_FOLLOW_UP_HINT_RE = re.compile(
    r"\b(remind|reminder|snooze|later|tomorrow|next\s+week|next\s+month|not\s+now|dismiss|ignore|done|complete|mark\s+done)\b",
    re.IGNORECASE,
)


CALENDAR_UPDATE_UNAVAILABLE_MESSAGE = (
    "I can schedule calendar events by voice right now. For updates or cancellations, "
    "open the event and tell me exactly what to change."
)


def _is_short_utterance(utterance: str, *, max_len: int = 120) -> bool:
    return len((utterance or "").strip()) <= max_len


def _looks_like_affirmative_response(utterance: str) -> bool:
    text = (utterance or "").strip()
    if not text or not _is_short_utterance(text):
        return False
    return _AFFIRMATIVE_RESPONSE_RE.search(text) is not None


def _looks_like_negative_response(utterance: str) -> bool:
    text = (utterance or "").strip()
    if not text or not _is_short_utterance(text):
        return False
    return _NEGATIVE_RESPONSE_RE.search(text) is not None


def _looks_like_follow_up_action(utterance: str) -> bool:
    text = (utterance or "").strip()
    if not text:
        return False
    return _FOLLOW_UP_HINT_RE.search(text) is not None


def build_plan(*, goal: SemanticGoal, state: WorldState) -> ExecutionPlan:
    plan = ExecutionPlan(goal=goal)
    utterance = goal.utterance or ""

    control_kind, _ = classify_control_intent(utterance)
    is_cancel = control_kind == "cancel_control"
    is_send = control_kind == "send_control"
    is_dismiss = control_kind == "dismiss_control"
    is_affirmative = _looks_like_affirmative_response(utterance)
    is_negative = _looks_like_negative_response(utterance)

    if state.notification_id and is_dismiss:
        plan.steps.append(
            PlanStep(
                "notification.dismiss",
                payload={"notification_id": state.notification_id},
            )
        )
        return plan

    if state.calendar_proposal_id and (is_cancel or is_negative):
        plan.steps.append(
            PlanStep(
                "calendar.cancel_proposal",
                payload={"proposal_id": state.calendar_proposal_id},
            )
        )
        return plan

    if state.calendar_proposal_id and (is_send or is_affirmative):
        plan.steps.append(
            PlanStep(
                "calendar.approve_proposal",
                payload={"proposal_id": state.calendar_proposal_id},
            )
        )
        return plan

    # When an active draft is visible in context, short confirm phrases should
    # execute draft actions directly even if Stage A intent parsing is uncertain.
    if state.draft_id and (is_send or is_affirmative):
        plan.steps.append(
            PlanStep(
                "email.handle_draft_command",
                payload={"draft_id": state.draft_id},
            )
        )
        return plan

    if state.draft_id and is_cancel:
        plan.steps.append(
            PlanStep(
                "email.handle_draft_command",
                payload={"draft_id": state.draft_id},
            )
        )
        return plan

    if state.calendar_proposal_id and goal.domain == "email" and goal.action == "modify_draft":
        plan.steps.append(
            PlanStep(
                "clarify",
                payload={
                    "message": "You are reviewing a calendar proposal. Edit the proposal fields in the panel and then confirm or cancel.",
                },
            )
        )
        return plan

    if goal.domain == "none" and state.follow_up_id and _looks_like_follow_up_action(utterance):
        plan.steps.append(PlanStep("followup.handle_command"))
        return plan

    # Support explicit send/cancel commands without notification context by
    # letting executor resolve the latest pending draft safely.
    if goal.domain == "none" and (is_send or is_cancel):
        plan.steps.append(PlanStep("email.handle_draft_command"))
        return plan

    draft_actions = {"send_draft", "cancel_draft", "modify_draft"}

    # Allow downstream draft resolution to recover from "active_draft" missing slot
    # by loading the latest pending draft when possible.
    non_recoverable_missing = [
        slot for slot in goal.missing_slots
        if not (
            goal.domain == "email"
            and goal.action in draft_actions
            and slot == "active_draft"
        )
    ]

    if non_recoverable_missing:
        plan.steps.append(PlanStep("clarify"))
        return plan

    if goal.domain == "email" and goal.action in draft_actions:
        payload: dict[str, str] = {}
        if state.draft_id:
            payload["draft_id"] = state.draft_id
        plan.steps.append(PlanStep("email.handle_draft_command", payload=payload))
        return plan

    if goal.domain == "calendar":
        if goal.action in {"update_event", "cancel_event"}:
            plan.steps.append(
                PlanStep(
                    "clarify",
                    payload={"message": CALENDAR_UPDATE_UNAVAILABLE_MESSAGE},
                )
            )
            return plan

        plan.steps.append(PlanStep("calendar.handle_command"))
        return plan

    if goal.domain == "email" and goal.action == "compose":
        plan.steps.append(PlanStep("email.handle_command"))
        return plan

    if goal.domain == "none" and state.has_notification_context:
        plan.steps.append(PlanStep("email.handle_command"))
        return plan

    plan.steps.append(PlanStep("clarify"))
    return plan
