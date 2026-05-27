from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from ...core import scheduler_wakeup
from ...db import db_session
from ..shared import notifications, reminders as reminder_service
from .email_sync_worker import _sleep_seconds_until


async def run_speech_reminder_worker(logger) -> None:
    while True:
        try:
            async with db_session() as db:
                due_reminders = await reminder_service.get_due_speech_reminders(db, limit=20)
                for reminder in due_reminders:
                    notification = await notifications.create_notification(db, reminder.message, "warning")
                    await reminder_service.mark_speech_reminder_fired(
                        db,
                        reminder=reminder,
                        notification_id=notification.id,
                    )
                    await notifications.push_notification(notification)
                    logger.info(
                        "speech_reminder_fired reminder_id=%s notification_id=%s fire_at=%s",
                        reminder.id,
                        notification.id,
                        reminder.fire_at,
                    )
                next_speech_reminder_at = await reminder_service.get_next_speech_reminder_at(db)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.exception("speech reminder loop error: %s", exc)
            await asyncio.sleep(60)
            continue

        sleep_seconds = _sleep_seconds_until(
            datetime.now(timezone.utc),
            next_speech_reminder_at,
            default_seconds=300,
        )
        await scheduler_wakeup.wait_for_scheduler_wakeup(sleep_seconds)