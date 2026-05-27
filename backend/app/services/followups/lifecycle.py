"""Follow-up item lifecycle service.

Responsibilities:
- create/update follow-up items from new email signals
- expose due reminders for scheduler
- handle snooze and dismiss user actions
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.runtime_config import get_llm_config
from ...core.scheduler_wakeup import notify_scheduler_wakeup
from ...db.tables import EmailItem, FollowUpActionRecord, FollowUpItem
from ...schemas import FollowUpItemDto
from ..ai.usage_store import record_llm_usage
from .extractor import extract_follow_up


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _to_dto(record: FollowUpItem) -> FollowUpItemDto:
    return FollowUpItemDto(
        id=record.id,
        email_id=record.email_id,
        status=record.status,  # type: ignore[arg-type]
        summary=record.summary,
        requested_action=record.requested_action,
        confidence=record.confidence,
        next_reminder_at=_as_utc(record.next_reminder_at).isoformat(),
        extracted_due_at=(
            _as_utc(record.extracted_due_at).isoformat() if record.extracted_due_at else None
        ),
        snoozed_until=(
            _as_utc(record.snoozed_until).isoformat() if record.snoozed_until else None
        ),
        reminder_count=int(record.reminder_count or 0),
        created_at=_as_utc(record.created_at).isoformat(),
        updated_at=_as_utc(record.updated_at).isoformat(),
    )


async def _append_action(
    db: AsyncSession,
    *,
    follow_up_id: str,
    action: str,
    details_json: dict,
) -> None:
    db.add(
        FollowUpActionRecord(
            id=str(uuid.uuid4()),
            follow_up_id=follow_up_id,
            action=action,
            details_json=details_json,
            created_at=datetime.now(timezone.utc),
        )
    )


async def upsert_followups_for_email_ids(
    db: AsyncSession,
    *,
    email_ids: list[str],
) -> list[FollowUpItemDto]:
    """Create/update follow-up records for newly seen emails.

    Idempotent by unique email_id.
    """
    if not email_ids:
        return []

    now = datetime.now(timezone.utc)
    created_or_updated: list[FollowUpItemDto] = []
    llm_config = await get_llm_config(db)

    result = await db.execute(
        select(EmailItem).where(EmailItem.id.in_(email_ids), EmailItem.is_read.is_(False))
    )
    emails = result.scalars().all()

    for email in emails:
        received_at = _as_utc(email.received_at)
        extracted = await extract_follow_up(db, email.subject, email.body_preview, received_at)
        if extracted.usage is not None:
            await record_llm_usage(
                db,
                interaction_kind="follow_up_extraction",
                provider=llm_config.provider,
                model=llm_config.model or "gpt-5.4-mini",
                usage=extracted.usage,
                source_email_id=email.id,
                metadata_json={"reasoning": extracted.reasoning},
            )
        if not extracted.requires_follow_up:
            continue

        existing_result = await db.execute(
            select(FollowUpItem).where(FollowUpItem.email_id == email.id)
        )
        existing = existing_result.scalar_one_or_none()

        if existing is None:
            reminder_at = now + extracted.first_reminder_after
            item = FollowUpItem(
                id=str(uuid.uuid4()),
                email_id=email.id,
                status="open",
                summary=extracted.summary,
                requested_action=extracted.requested_action,
                confidence=extracted.confidence,
                extracted_due_at=extracted.extracted_due_at,
                next_reminder_at=reminder_at,
                reminder_count=0,
                metadata_json={"reasoning": extracted.reasoning},
                created_at=now,
                updated_at=now,
            )
            db.add(item)
            await _append_action(
                db,
                follow_up_id=item.id,
                action="created",
                details_json={
                    "confidence": extracted.confidence,
                    "next_reminder_at": reminder_at.isoformat(),
                },
            )
            created_or_updated.append(_to_dto(item))
            continue

        if existing.status in {"dismissed", "done"}:
            continue

        # Keep open items fresh in case email body preview changed.
        existing.summary = extracted.summary
        existing.requested_action = extracted.requested_action
        existing.confidence = extracted.confidence
        existing.extracted_due_at = extracted.extracted_due_at
        existing.metadata_json = {
            **(existing.metadata_json or {}),
            "reasoning": extracted.reasoning,
            "last_refresh_at": now.isoformat(),
        }
        existing.updated_at = now
        created_or_updated.append(_to_dto(existing))

    if created_or_updated:
        await db.commit()

    return created_or_updated


def _next_interval_after_reminder(reminder_count: int) -> timedelta:
    # 1st reminder cadence is set at extraction; follow-up escalations widen.
    if reminder_count <= 1:
        return timedelta(hours=24)
    if reminder_count == 2:
        return timedelta(hours=48)
    return timedelta(hours=72)


async def get_due_followups(db: AsyncSession, *, limit: int = 10) -> list[FollowUpItem]:
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(FollowUpItem)
        .where(
            FollowUpItem.status.in_(["open", "snoozed"]),
            FollowUpItem.next_reminder_at <= now,
        )
        .order_by(FollowUpItem.next_reminder_at.asc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_next_followup_due_at(db: AsyncSession) -> datetime | None:
    result = await db.execute(
        select(FollowUpItem.next_reminder_at)
        .where(FollowUpItem.status.in_(["open", "snoozed"]))
        .order_by(FollowUpItem.next_reminder_at.asc())
        .limit(1)
    )
    next_due_at = result.scalar_one_or_none()
    if next_due_at is None:
        return None
    return _as_utc(next_due_at)


async def mark_reminder_sent(db: AsyncSession, item: FollowUpItem) -> FollowUpItemDto:
    now = datetime.now(timezone.utc)
    item.status = "open"
    item.reminder_count += 1
    item.last_reminded_at = now
    item.snoozed_until = None
    item.next_reminder_at = now + _next_interval_after_reminder(item.reminder_count)
    item.updated_at = now

    await _append_action(
        db,
        follow_up_id=item.id,
        action="reminder_sent",
        details_json={
            "reminder_count": item.reminder_count,
            "next_reminder_at": _as_utc(item.next_reminder_at).isoformat(),
        },
    )
    await db.commit()
    return _to_dto(item)


async def list_followups(
    db: AsyncSession,
    *,
    status: str | None = None,
    limit: int = 100,
) -> list[FollowUpItemDto]:
    query = select(FollowUpItem).order_by(FollowUpItem.next_reminder_at.asc()).limit(limit)
    if status:
        query = query.where(FollowUpItem.status == status)
    result = await db.execute(query)
    return [_to_dto(item) for item in result.scalars().all()]


async def get_followup_by_id(db: AsyncSession, *, follow_up_id: str) -> FollowUpItemDto | None:
    result = await db.execute(select(FollowUpItem).where(FollowUpItem.id == follow_up_id))
    item = result.scalar_one_or_none()
    if item is None:
        return None
    return _to_dto(item)


async def dismiss_followup(db: AsyncSession, *, follow_up_id: str) -> FollowUpItemDto | None:
    result = await db.execute(select(FollowUpItem).where(FollowUpItem.id == follow_up_id))
    item = result.scalar_one_or_none()
    if item is None:
        return None

    now = datetime.now(timezone.utc)
    item.status = "dismissed"
    item.dismissed_at = now
    item.updated_at = now
    await _append_action(db, follow_up_id=item.id, action="dismissed", details_json={})
    await db.commit()
    notify_scheduler_wakeup()
    return _to_dto(item)


async def snooze_followup(
    db: AsyncSession,
    *,
    follow_up_id: str,
    snoozed_until: datetime,
) -> FollowUpItemDto | None:
    result = await db.execute(select(FollowUpItem).where(FollowUpItem.id == follow_up_id))
    item = result.scalar_one_or_none()
    if item is None:
        return None

    now = datetime.now(timezone.utc)
    snoozed_until = _as_utc(snoozed_until)
    item.status = "snoozed"
    item.snoozed_until = snoozed_until
    item.next_reminder_at = snoozed_until
    item.updated_at = now
    await _append_action(
        db,
        follow_up_id=item.id,
        action="snoozed",
        details_json={"snoozed_until": snoozed_until.isoformat()},
    )
    await db.commit()
    notify_scheduler_wakeup()
    return _to_dto(item)


async def complete_followup(db: AsyncSession, *, follow_up_id: str) -> FollowUpItemDto | None:
    result = await db.execute(select(FollowUpItem).where(FollowUpItem.id == follow_up_id))
    item = result.scalar_one_or_none()
    if item is None:
        return None

    now = datetime.now(timezone.utc)
    item.status = "done"
    item.completed_at = now
    item.updated_at = now
    await _append_action(db, follow_up_id=item.id, action="completed", details_json={})
    await db.commit()
    notify_scheduler_wakeup()
    return _to_dto(item)
