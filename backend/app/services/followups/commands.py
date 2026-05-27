"""Handle in-context user commands for follow-up reminders.

This runs inside the existing transcript flow: if the transcript is associated
with a follow-up notification, we parse command intent and execute action.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.runtime_config import get_llm_config
from ...db.tables import FollowUpItem, NotificationRecord
from ..common.followup_markers import extract_follow_up_id, strip_follow_up_marker
from ..interaction.client_feedback import ClientInteractionOutcome
from ..ai.usage_store import record_llm_usage
from ..shared import notifications as notification_service
from ..shared import reminders as reminder_service
from ..shared.outcome import ServiceExecutionOutcome
from . import lifecycle as follow_up_service
from .parser import ParsedFollowUpAction, parse_follow_up_user_action

logger = logging.getLogger(__name__)


def _extract_follow_up_id_from_message(message: str) -> str | None:
    return extract_follow_up_id(message)


def _strip_follow_up_marker(message: str) -> str:
    return strip_follow_up_marker(message)


def _format_local_due_time(target: datetime) -> str:
    local_target = target.astimezone()
    return local_target.strftime("%a, %b %d at %I:%M %p").replace(" 0", " ")


def _build_snooze_display_text(target: datetime) -> str:
    return f"Scheduled reminder for {_format_local_due_time(target)}."


def _build_action_display_text(action: str) -> str | None:
    if action == "dismiss":
        return "Dismissed this notification."
    if action == "complete":
        return "Marked this follow-up as complete."
    return None


async def _get_notification(
    db: AsyncSession,
    notification_id: str,
) -> NotificationRecord | None:
    notif_result = await db.execute(
        select(NotificationRecord).where(NotificationRecord.id == notification_id)
    )
    return notif_result.scalar_one_or_none()


async def _dismiss_notification(
    db: AsyncSession,
    notification_id: str | None,
) -> object | None:
    if not notification_id:
        return None
    return await notification_service.dismiss_notification(db, notification_id)


async def _create_ad_hoc_reminder_notification(
    db: AsyncSession,
    *,
    reminder_message: str,
    fire_at: datetime,
    source_notification_id: str | None,
    source_transcript: str,
) -> datetime:
    logger.info(
        "schedule_ad_hoc_reminder_persisted fire_at=%s message=%r",
        fire_at.isoformat(),
        reminder_message,
    )
    reminder = await reminder_service.create_speech_reminder(
        db,
        message=f"Reminder: {reminder_message}",
        fire_at=fire_at,
        source_notification_id=source_notification_id,
        source_transcript=source_transcript,
    )
    logger.info(
        "ad_hoc_reminder_record_created reminder_id=%s fire_at=%s source_notification_id=%s",
        reminder.id,
        fire_at.isoformat(),
        source_notification_id,
    )
    return fire_at


async def _resolve_follow_up_context(
    db: AsyncSession,
    *,
    notification_id: str | None,
) -> tuple[str, str, str] | None:
    # 1) Prefer explicit notification context from frontend.
    if notification_id:
        notification = await _get_notification(db, notification_id)
        if notification is not None:
            follow_up_id = _extract_follow_up_id_from_message(notification.message)
            if follow_up_id:
                return notification.id, follow_up_id, "explicit"

    # 2) Fallback: use the newest unread notification that carries [fu:...] marker.
    recent_result = await db.execute(
        select(NotificationRecord)
        .where(NotificationRecord.read.is_(False))
        .order_by(NotificationRecord.timestamp.desc())
        .limit(25)
    )
    for candidate in recent_result.scalars().all():
        follow_up_id = _extract_follow_up_id_from_message(candidate.message)
        if follow_up_id:
            return candidate.id, follow_up_id, "fallback_latest_unread_followup"

    return None


async def _execute_follow_up_action(
    db: AsyncSession,
    *,
    parsed: ParsedFollowUpAction,
    follow_up_id: str,
    notification_to_dismiss_id: str | None,
    correlation_id: str | None,
    resolved_notification_id: str,
) -> ServiceExecutionOutcome:
    if parsed.action == "snooze":
        now_utc = datetime.now(timezone.utc)
        snoozed_until = parsed.resolve_snooze_at(now_utc=now_utc) or (now_utc + timedelta(days=1))
        delta_minutes = max(1, int((snoozed_until - now_utc).total_seconds() / 60))
        updated = await follow_up_service.snooze_followup(
            db,
            follow_up_id=follow_up_id,
            snoozed_until=snoozed_until,
        )
        if updated is None:
            logger.info(
                "follow_up_command_outcome correlation_id=%s notification_id=%s follow_up_id=%s action=snooze executed=false reason=follow_up_not_found",
                correlation_id,
                resolved_notification_id,
                follow_up_id,
            )
            return ServiceExecutionOutcome()

        dismissed_notification = await _dismiss_notification(db, notification_to_dismiss_id)
        logger.info(
            "follow_up_command_outcome correlation_id=%s notification_id=%s follow_up_id=%s action=snooze executed=true snooze_minutes=%s next_reminder_at=%s",
            correlation_id,
            notification_to_dismiss_id,
            follow_up_id,
            delta_minutes,
            updated.next_reminder_at,
        )
        return ServiceExecutionOutcome(
            result=parsed.action,
            display_text=_build_snooze_display_text(snoozed_until),
            interaction=ClientInteractionOutcome(
                dismissed_notification=dismissed_notification,
                close_window=True,
            ),
        )

    if parsed.action == "dismiss":
        updated = await follow_up_service.dismiss_followup(db, follow_up_id=follow_up_id)
    elif parsed.action == "complete":
        updated = await follow_up_service.complete_followup(db, follow_up_id=follow_up_id)
    else:
        return ServiceExecutionOutcome()

    if updated is None:
        logger.info(
            "follow_up_command_outcome correlation_id=%s notification_id=%s follow_up_id=%s action=%s executed=false reason=follow_up_not_found",
            correlation_id,
            resolved_notification_id,
            follow_up_id,
            parsed.action,
        )
        return ServiceExecutionOutcome()

    dismissed_notification = await _dismiss_notification(db, notification_to_dismiss_id)
    logger.info(
        "follow_up_command_outcome correlation_id=%s notification_id=%s follow_up_id=%s action=%s executed=true",
        correlation_id,
        notification_to_dismiss_id,
        follow_up_id,
        parsed.action,
    )
    return ServiceExecutionOutcome(
        result=parsed.action,
        display_text=_build_action_display_text(parsed.action),
        interaction=ClientInteractionOutcome(
            dismissed_notification=dismissed_notification,
            close_window=True,
        ),
    )


def _fallback_feedback_interaction(
    *,
    notification_id: str | None,
    transcript_text: str,
) -> ClientInteractionOutcome:
    has_user_feedback = bool(transcript_text.strip())
    if not notification_id or not has_user_feedback:
        return ClientInteractionOutcome()
    return ClientInteractionOutcome(
        dismiss_notification_id=notification_id,
        close_window=True,
    )


async def handle_follow_up_command_from_transcript(
    db: AsyncSession,
    *,
    notification_id: str | None,
    transcript_text: str,
    correlation_id: str | None = None,
) -> ServiceExecutionOutcome:
    """Parse and execute a voice command and return its structured outcome."""
    logger.info(
        "handle_follow_up_command_from_transcript START notification_id=%s transcript=%r",
        notification_id,
        transcript_text,
    )
    llm_config = await get_llm_config(db)
    parse_failed = False
    try:
        parsed = await parse_follow_up_user_action(db, transcript_text)
    except Exception as exc:
        logger.warning(
            "follow_up_parser failed, returning no-op error=%s utterance=%r",
            exc,
            transcript_text,
        )
        parse_failed = True
        parsed = ParsedFollowUpAction(
            action="none",
            snooze_minutes=None,
            snooze_until=None,
            reasoning=f"parse_error:{type(exc).__name__}",
        )
    logger.info(
        "parsed action action=%s snooze_minutes=%s snooze_until=%s reasoning=%s",
        parsed.action,
        parsed.snooze_minutes,
        parsed.snooze_until,
        parsed.reasoning,
    )

    if parse_failed:
        return ServiceExecutionOutcome(
            display_text="I couldn't understand that follow-up command. Please try again.",
        )

    resolved = await _resolve_follow_up_context(db, notification_id=notification_id)
    follow_up_email_id: str | None = None
    if resolved is not None:
        follow_up_result = await db.execute(select(FollowUpItem).where(FollowUpItem.id == resolved[1]))
        follow_up_record = follow_up_result.scalar_one_or_none()
        if follow_up_record is not None:
            follow_up_email_id = follow_up_record.email_id

    if parsed.usage is not None:
        await record_llm_usage(
            db,
            interaction_kind="follow_up_command_parse",
            provider=llm_config.provider,
            model=llm_config.model or "gpt-5.4-mini",
            usage=parsed.usage,
            source_email_id=follow_up_email_id,
            notification_id=notification_id,
            metadata_json={"correlation_id": correlation_id, "reasoning": parsed.reasoning},
        )

    if resolved is None:
        if parsed.action == "none":
            logger.info(
                "follow_up_command_outcome correlation_id=%s notification_id=%s follow_up_id=%s action=%s executed=false reason=no_followup_context_no_action",
                correlation_id,
                notification_id,
                None,
                "none",
            )
            return ServiceExecutionOutcome(
                interaction=_fallback_feedback_interaction(
                    notification_id=notification_id,
                    transcript_text=transcript_text,
                )
            )

        if notification_id:
            notification = await _get_notification(db, notification_id)
            if notification is not None:
                dismissed_notification = await _dismiss_notification(db, notification_id)

                if parsed.action == "snooze":
                    fire_at = parsed.resolve_snooze_at(now_utc=datetime.now(timezone.utc)) or (
                        datetime.now(timezone.utc) + timedelta(days=1)
                    )
                    base_message = _strip_follow_up_marker(notification.message)
                    reminder_message = base_message or "Follow up on your last notification."
                    fire_at = await _create_ad_hoc_reminder_notification(
                        db,
                        reminder_message=reminder_message,
                        fire_at=fire_at,
                        source_notification_id=notification_id,
                        source_transcript=transcript_text,
                    )
                else:
                    fire_at = None

                logger.info(
                    "follow_up_command_outcome correlation_id=%s notification_id=%s follow_up_id=%s action=%s executed=true reason=ad_hoc_without_followup_context",
                    correlation_id,
                    notification_id,
                    None,
                    parsed.action,
                )
                return ServiceExecutionOutcome(
                    result=parsed.action,
                    display_text=(
                        _build_snooze_display_text(fire_at)
                        if parsed.action == "snooze" and fire_at is not None
                        else _build_action_display_text(parsed.action)
                    ),
                    interaction=ClientInteractionOutcome(
                        dismissed_notification=dismissed_notification,
                        close_window=True,
                    ),
                )

        logger.info(
            "follow_up_command_outcome correlation_id=%s notification_id=%s follow_up_id=%s action=%s executed=false reason=no_followup_context",
            correlation_id,
            notification_id,
            None,
            parsed.action,
        )
        return ServiceExecutionOutcome(
            interaction=_fallback_feedback_interaction(
                notification_id=notification_id,
                transcript_text=transcript_text,
            )
        )
    resolved_notification_id, follow_up_id, context_source = resolved
    notification_to_dismiss_id = notification_id or resolved_notification_id

    logger.info(
        "follow_up_command_parsed correlation_id=%s notification_id=%s follow_up_id=%s context_source=%s action=%s snooze_minutes=%s snooze_until=%s reasoning=%s transcript=%r",
        correlation_id,
        resolved_notification_id,
        follow_up_id,
        context_source,
        parsed.action,
        parsed.snooze_minutes,
        parsed.snooze_until,
        parsed.reasoning,
        transcript_text,
    )
    if parsed.action == "none":
        logger.info(
            "follow_up_command_outcome correlation_id=%s notification_id=%s follow_up_id=%s action=none executed=false reason=no_action",
            correlation_id,
            resolved_notification_id,
            follow_up_id,
        )
        return ServiceExecutionOutcome(
            interaction=_fallback_feedback_interaction(
                notification_id=notification_id,
                transcript_text=transcript_text,
            )
        )
    return await _execute_follow_up_action(
        db,
        parsed=parsed,
        follow_up_id=follow_up_id,
        notification_to_dismiss_id=notification_to_dismiss_id,
        correlation_id=correlation_id,
        resolved_notification_id=resolved_notification_id,
    )
