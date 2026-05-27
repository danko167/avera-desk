"""Deterministic reminder persistence and dispatch helpers."""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.scheduler_wakeup import notify_scheduler_wakeup
from ...db.tables import SpeechReminderRecord


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


async def create_speech_reminder(
    db: AsyncSession,
    *,
    message: str,
    fire_at: datetime,
    source_notification_id: str | None = None,
    source_transcript: str | None = None,
) -> SpeechReminderRecord:
    now = datetime.now(timezone.utc)
    record = SpeechReminderRecord(
        id=str(uuid.uuid4()),
        message=message,
        fire_at=_as_utc(fire_at),
        status="scheduled",
        source_notification_id=source_notification_id,
        source_transcript=source_transcript,
        metadata_json={},
        created_at=now,
        updated_at=now,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    notify_scheduler_wakeup()
    return record


async def get_due_speech_reminders(
    db: AsyncSession,
    *,
    limit: int = 10,
) -> list[SpeechReminderRecord]:
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(SpeechReminderRecord)
        .where(
            SpeechReminderRecord.status == "scheduled",
            SpeechReminderRecord.fire_at <= now,
        )
        .order_by(SpeechReminderRecord.fire_at.asc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_next_speech_reminder_at(db: AsyncSession) -> datetime | None:
    result = await db.execute(
        select(SpeechReminderRecord.fire_at)
        .where(SpeechReminderRecord.status == "scheduled")
        .order_by(SpeechReminderRecord.fire_at.asc())
        .limit(1)
    )
    next_due_at = result.scalar_one_or_none()
    if next_due_at is None:
        return None
    return _as_utc(next_due_at)


async def mark_speech_reminder_fired(
    db: AsyncSession,
    *,
    reminder: SpeechReminderRecord,
    notification_id: str,
) -> None:
    now = datetime.now(timezone.utc)
    reminder.status = "fired"
    reminder.notification_id = notification_id
    reminder.fired_at = now
    reminder.updated_at = now
    reminder.metadata_json = {
        **(reminder.metadata_json or {}),
        "fired_notification_id": notification_id,
        "fired_at": now.isoformat(),
    }
    await db.commit()
