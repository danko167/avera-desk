from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ....db.tables import CalendarProposalRecord, EmailDraftRecord
from ...interaction.client_feedback import ClientInteractionOutcome
from ...shared.outcome import ServiceExecutionOutcome
from .clarification import resolve_clarification
from .models import ExecutionPlan, SemanticGoal, WorldState


CalendarHandler = Callable[..., Awaitable[ServiceExecutionOutcome]]
EmailHandler = Callable[..., Awaitable[ServiceExecutionOutcome]]
DraftHandler = Callable[..., Awaitable[ServiceExecutionOutcome]]
FollowupHandler = Callable[..., Awaitable[ServiceExecutionOutcome]]
ApproveProposal = Callable[..., Awaitable[object | None]]
CancelProposal = Callable[..., Awaitable[object | None]]


@dataclass(slots=True)
class EngineHandlers:
    handle_calendar_command: CalendarHandler
    handle_email_command: EmailHandler
    handle_email_draft_command: DraftHandler
    handle_followup_command: FollowupHandler
    approve_calendar_proposal: ApproveProposal
    cancel_calendar_proposal: CancelProposal


def _calendar_terminal_status_message(status: str) -> str:
    if status == "approved":
        return "This calendar proposal is already approved."
    if status == "rejected":
        return "This calendar proposal was already rejected."
    if status == "canceled":
        return "This calendar proposal is already canceled."
    return "This calendar proposal is no longer actionable."


async def _get_calendar_proposal_status(db: AsyncSession, *, proposal_id: str) -> str | None:
    result = await db.execute(select(CalendarProposalRecord.status).where(CalendarProposalRecord.id == proposal_id))
    value = result.scalar_one_or_none()
    if isinstance(value, str):
        return value.strip() or None
    return None


async def _resolve_latest_pending_draft(db: AsyncSession) -> str | None:
    result = await db.execute(
        select(EmailDraftRecord.id)
        .where(EmailDraftRecord.status == "pending")
        .order_by(EmailDraftRecord.updated_at.desc())
        .limit(1)
    )
    value = result.scalar_one_or_none()
    if isinstance(value, str):
        return value.strip() or None
    return None


async def execute_plan(
    db: AsyncSession,
    *,
    goal: SemanticGoal,
    state: WorldState,
    plan: ExecutionPlan,
    correlation_id: str | None,
    handlers: EngineHandlers,
) -> ServiceExecutionOutcome:
    for step in plan.steps:
        if step.capability == "clarify":
            message = str(step.payload.get("message") or "").strip() or resolve_clarification(goal)
            return ServiceExecutionOutcome(
                result="intent_clarification_needed",
                display_text=message,
            )

        if step.capability == "notification.dismiss":
            notification_id = str(step.payload.get("notification_id") or "").strip() or state.notification_id
            if not notification_id:
                return ServiceExecutionOutcome(
                    result="intent_clarification_needed",
                    display_text="There is no active notification to dismiss.",
                )
            return ServiceExecutionOutcome(
                result="dismiss",
                display_text="Notification dismissed.",
                interaction=ClientInteractionOutcome(
                    dismiss_notification_id=notification_id,
                    close_window=True,
                ),
            )

        if step.capability == "calendar.cancel_proposal":
            proposal_id = str(step.payload.get("proposal_id") or "").strip()
            status = await _get_calendar_proposal_status(db, proposal_id=proposal_id)
            if status in {"awaiting_user_decision", "proposed"}:
                canceled = await handlers.cancel_calendar_proposal(db, proposal_id=proposal_id)
                if canceled is not None:
                    return ServiceExecutionOutcome(
                        result="calendar_proposal_canceled",
                        display_text="Calendar proposal canceled.",
                        interaction=ClientInteractionOutcome(
                            dismiss_notification_id=state.notification_id,
                            close_window=True,
                        ),
                    )
            if status:
                return ServiceExecutionOutcome(
                    result="intent_clarification_needed",
                    display_text=_calendar_terminal_status_message(status),
                )
            return ServiceExecutionOutcome(result="intent_clarification_needed", display_text="Calendar proposal not found.")

        if step.capability == "calendar.approve_proposal":
            proposal_id = str(step.payload.get("proposal_id") or "").strip()
            status = await _get_calendar_proposal_status(db, proposal_id=proposal_id)
            if status in {"awaiting_user_decision", "proposed"}:
                try:
                    approved = await handlers.approve_calendar_proposal(db, proposal_id=proposal_id)
                except RuntimeError as exc:
                    return ServiceExecutionOutcome(result="intent_clarification_needed", display_text=str(exc))
                if approved is not None:
                    attendees_raw = getattr(approved, "attendees", []) or []
                    attendees = [value for value in attendees_raw if str(value).strip()]
                    display_text = (
                        "Calendar event created on your calendar. No attendee email invites were sent because no attendees were set."
                        if len(attendees) == 0
                        else "Calendar proposal approved and invites sent."
                    )
                    return ServiceExecutionOutcome(
                        result="calendar_proposal_approved",
                        display_text=display_text,
                        interaction=ClientInteractionOutcome(
                            dismiss_notification_id=state.notification_id,
                            close_window=True,
                        ),
                    )
            if status:
                return ServiceExecutionOutcome(
                    result="intent_clarification_needed",
                    display_text=_calendar_terminal_status_message(status),
                )
            return ServiceExecutionOutcome(result="intent_clarification_needed", display_text="Calendar proposal not found.")

        if step.capability == "followup.handle_command":
            outcome = await handlers.handle_followup_command(
                db,
                notification_id=state.notification_id,
                transcript_text=goal.utterance,
                correlation_id=correlation_id,
            )
            if outcome.result is not None:
                return outcome
            continue

        if step.capability == "email.handle_draft_command":
            draft_id = str(step.payload.get("draft_id") or "").strip() or state.draft_id
            if not draft_id:
                draft_id = await _resolve_latest_pending_draft(db)
            if not draft_id:
                return ServiceExecutionOutcome(
                    result="intent_clarification_needed",
                    display_text="There is no active draft right now. Say 'write an email' first.",
                )
            return await handlers.handle_email_draft_command(
                db,
                draft_id=draft_id,
                transcript_text=goal.utterance,
                notification_id=state.notification_id,
            )

        if step.capability == "calendar.handle_command":
            outcome = await handlers.handle_calendar_command(
                db,
                notification_id=state.notification_id,
                transcript_text=goal.utterance,
                correlation_id=correlation_id,
            )
            if outcome.result is not None:
                return outcome
            continue

        if step.capability == "email.handle_command":
            outcome = await handlers.handle_email_command(
                db,
                notification_id=state.notification_id,
                transcript_text=goal.utterance,
                correlation_id=correlation_id,
            )
            if outcome.result is not None:
                return outcome
            continue

    return ServiceExecutionOutcome(
        result="intent_clarification_needed",
        display_text="I did not detect a clear action. Try: 'reply that I approve', 'send it', or 'remind me tomorrow'.",
    )
