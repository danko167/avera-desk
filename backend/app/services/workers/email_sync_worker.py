from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging

from ...core import scheduler_wakeup
from ...db import db_session
from ...integrations.email_provider import get_oauth_module, normalize_email_provider
from ...schemas import FollowUpItemDto
from ..email import sync as email_sync
from ..followups import lifecycle as follow_ups
from ..shared.notification_content import (
    build_follow_up_notification_details,
    build_follow_up_notification_message,
    build_new_email_notification_details,
    build_new_email_notification_message,
)
from ..shared import notifications
from ..shared.preferences import get_settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class EmailSyncRuntimeState:
    next_sync_at: datetime | None = None
    last_sync_started_at: datetime | None = None
    last_sync_finished_at: datetime | None = None


_email_sync_runtime_state = EmailSyncRuntimeState()


def _sleep_seconds_until(
    now: datetime,
    *targets: datetime | None,
    default_seconds: float,
) -> float:
    delays = [max(0.0, (target - now).total_seconds()) for target in targets if target is not None]
    if not delays:
        return max(1.0, default_seconds)
    return max(1.0, min(delays))
async def push_new_email_notifications(
    db,
    *,
    new_emails: list[dict],
    created_followups: list[FollowUpItemDto],
) -> None:
    followup_by_email_id = {item.email_id: item for item in created_followups}

    for email in new_emails:
        email_id = email["id"]
        fu_item = followup_by_email_id.get(email_id)
        
        details = build_new_email_notification_details(
            from_email=email.get("from"),
            subject=email.get("subject"),
            body_preview=email.get("body_preview"),
            followup_id=(fu_item.id if fu_item else None),
            followup_summary=(fu_item.summary if fu_item else None),
        )
        message = build_new_email_notification_message(from_email=email.get("from"))

        notification = await notifications.create_notification(
            db,
            message,
            "info",
            source_email_id=email_id,
            details=details,
        )
        await notifications.push_notification(notification)
        logger.info("email_new_message_alert subject=%s", email["subject"])


def get_email_sync_runtime_state() -> EmailSyncRuntimeState:
    return EmailSyncRuntimeState(
        next_sync_at=_email_sync_runtime_state.next_sync_at,
        last_sync_started_at=_email_sync_runtime_state.last_sync_started_at,
        last_sync_finished_at=_email_sync_runtime_state.last_sync_finished_at,
    )


async def run_email_sync_worker() -> None:
    next_email_sync_at: datetime | None = None
    while True:
        try:
            async with db_session() as db:
                settings = await get_settings(db)
                email_provider = normalize_email_provider(settings.get("email_provider"))
                oauth = get_oauth_module(email_provider)
                sync_interval_minutes = int(settings.get("email_sync_interval_minutes", 5))
                sync_interval_minutes = max(1, min(60, sync_interval_minutes))
                sync_interval_seconds = sync_interval_minutes * 60
                now = datetime.now(timezone.utc)

                if next_email_sync_at is None:
                    next_email_sync_at = now

                if oauth.is_authenticated() and now >= next_email_sync_at:
                    _email_sync_runtime_state.last_sync_started_at = now
                    _, new_emails = await email_sync.sync_inbox(db)
                    created_followups = await follow_ups.upsert_followups_for_email_ids(
                        db,
                        email_ids=[email["id"] for email in new_emails],
                    )
                    await push_new_email_notifications(
                        db,
                        new_emails=new_emails,
                        created_followups=created_followups,
                    )

                    _email_sync_runtime_state.last_sync_finished_at = datetime.now(timezone.utc)
                    next_email_sync_at = _email_sync_runtime_state.last_sync_finished_at + timedelta(seconds=sync_interval_seconds)
                elif not oauth.is_authenticated():
                    next_email_sync_at = now + timedelta(seconds=sync_interval_seconds)

                due_items = await follow_ups.get_due_followups(db, limit=10)
                for due in due_items:
                    reminder_message = build_follow_up_notification_message(
                        follow_up_id=due.id,
                        summary=due.summary,
                        prefix="Follow-up reminder:",
                    )
                    reminder_notification = await notifications.create_notification(
                        db,
                        reminder_message,
                        "warning",
                        source_email_id=due.email_id,
                        details=build_follow_up_notification_details(summary=due.summary),
                    )
                    await notifications.push_notification(reminder_notification)
                    await follow_ups.mark_reminder_sent(db, due)

                next_followup_due_at = await follow_ups.get_next_followup_due_at(db)

            _email_sync_runtime_state.next_sync_at = next_email_sync_at
            sleep_seconds = _sleep_seconds_until(
                datetime.now(timezone.utc),
                next_email_sync_at,
                next_followup_due_at,
                default_seconds=sync_interval_seconds,
            )
            await scheduler_wakeup.wait_for_scheduler_wakeup(sleep_seconds)
        except asyncio.CancelledError:
            _email_sync_runtime_state.next_sync_at = None
            break
        except Exception as exc:
            _email_sync_runtime_state.last_sync_finished_at = datetime.now(timezone.utc)
            _email_sync_runtime_state.next_sync_at = _email_sync_runtime_state.last_sync_finished_at + timedelta(seconds=60)
            logger.exception("email_sync_worker_error error=%s", exc)
            await asyncio.sleep(60)


