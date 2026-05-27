import uuid
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core import websocket_state as state
from ...db.tables import EmailItem, LlmUsageRecord, NotificationRecord
from ...schemas import Notification, NotificationDetails, NotificationType


def _parse_notification_details(record: NotificationRecord) -> NotificationDetails | None:
    if not record.details_json:
        return None
    try:
        return NotificationDetails(**record.details_json)
    except (TypeError, ValueError):
        return None


def _notification_usage_keys(record: NotificationRecord, details: NotificationDetails | None) -> list[str]:
    keys: list[str] = [record.id]
    source_notification_id = (details.source_notification_id if details else None) or ""
    source_notification_id = source_notification_id.strip()
    if source_notification_id and source_notification_id != record.id:
        keys.append(source_notification_id)
    return keys


def _notification_source_email_id(record: NotificationRecord) -> str | None:
    source_email_id = (record.source_email_id or "").strip()
    return source_email_id or None


def _record_to_pydantic(
    record: NotificationRecord,
    *,
    llm_prompt_tokens: int | None = None,
    llm_completion_tokens: int | None = None,
    llm_total_tokens: int | None = None,
) -> Notification:
    details = _parse_notification_details(record)
    
    return Notification(
        id=record.id,
        message=record.message,
        type=record.type,  # type: ignore[arg-type]
        source_email_id=record.source_email_id,
        details=details,
        timestamp=record.timestamp.isoformat(),
        read=record.read,
        dismissed_at=(
            record.dismissed_at.isoformat() if record.dismissed_at else None
        ),
        llm_prompt_tokens=llm_prompt_tokens,
        llm_completion_tokens=llm_completion_tokens,
        llm_total_tokens=llm_total_tokens,
    )


async def _get_llm_usage_rows(
    db: AsyncSession,
    notification_ids: list[str],
    source_email_ids: list[str],
) -> list[tuple[str, str | None, str | None, int, int, int]]:
    if not notification_ids and not source_email_ids:
        return []

    predicates = []
    if notification_ids:
        predicates.append(LlmUsageRecord.notification_id.in_(notification_ids))
    if source_email_ids:
        predicates.append(LlmUsageRecord.source_email_id.in_(source_email_ids))

    result = await db.execute(
        select(
            LlmUsageRecord.id,
            LlmUsageRecord.notification_id,
            LlmUsageRecord.source_email_id,
            LlmUsageRecord.prompt_tokens,
            LlmUsageRecord.completion_tokens,
            LlmUsageRecord.total_tokens,
        ).where(or_(*predicates))
    )
    return [
        (
            str(row_id),
            (str(notification_id).strip() if notification_id else None),
            (str(source_email_id).strip() if source_email_id else None),
            int(prompt_tokens or 0),
            int(completion_tokens or 0),
            int(total_tokens or 0),
        )
        for row_id, notification_id, source_email_id, prompt_tokens, completion_tokens, total_tokens in result.all()
    ]


def _aggregate_usage_for_notification(
    usage_rows: list[tuple[str, str | None, str | None, int, int, int]],
    *,
    notification_ids: list[str],
    source_email_id: str | None,
) -> dict[str, int]:
    aggregated = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }
    seen_row_ids: set[str] = set()
    notification_id_set = {key for key in notification_ids if key}
    clean_source_email_id = (source_email_id or "").strip() or None

    for row_id, row_notification_id, row_source_email_id, prompt_tokens, completion_tokens, total_tokens in usage_rows:
        if row_id in seen_row_ids:
            continue

        matches_notification = bool(row_notification_id and row_notification_id in notification_id_set)
        matches_source_email = bool(
            clean_source_email_id
            and row_notification_id is None
            and row_source_email_id == clean_source_email_id
        )
        if not matches_notification and not matches_source_email:
            continue

        seen_row_ids.add(row_id)
        aggregated["prompt_tokens"] += prompt_tokens
        aggregated["completion_tokens"] += completion_tokens
        aggregated["total_tokens"] += total_tokens
    return aggregated


async def _enrich_notifications(db: AsyncSession, records: list[NotificationRecord]) -> list[Notification]:
    details_by_id = {record.id: _parse_notification_details(record) for record in records}
    notification_ids = list(
        {
            key
            for record in records
            for key in _notification_usage_keys(record, details_by_id[record.id])
        }
    )
    source_email_ids = list(
        {
            source_email_id
            for record in records
            if (source_email_id := _notification_source_email_id(record)) is not None
        }
    )
    usage_rows = await _get_llm_usage_rows(db, notification_ids, source_email_ids)
    return [
        _record_to_pydantic(
            record,
            llm_prompt_tokens=_aggregate_usage_for_notification(
                usage_rows,
                notification_ids=_notification_usage_keys(record, details_by_id[record.id]),
                source_email_id=_notification_source_email_id(record),
            ).get("prompt_tokens"),
            llm_completion_tokens=_aggregate_usage_for_notification(
                usage_rows,
                notification_ids=_notification_usage_keys(record, details_by_id[record.id]),
                source_email_id=_notification_source_email_id(record),
            ).get("completion_tokens"),
            llm_total_tokens=_aggregate_usage_for_notification(
                usage_rows,
                notification_ids=_notification_usage_keys(record, details_by_id[record.id]),
                source_email_id=_notification_source_email_id(record),
            ).get("total_tokens"),
        )
        for record in records
    ]


async def create_notification(
    db: AsyncSession,
    message: str,
    notification_type: NotificationType = "info",
    source_email_id: str | None = None,
    details: dict | None = None,
) -> Notification:
    """Persist a new notification and return its Pydantic representation."""
    record = NotificationRecord(
        id=str(uuid.uuid4()),
        message=message,
        type=notification_type,
        source_email_id=source_email_id,
        details_json=details,
        timestamp=datetime.now(timezone.utc),
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    details_obj = _parse_notification_details(record)
    usage_rows = await _get_llm_usage_rows(
        db,
        _notification_usage_keys(record, details_obj),
        [_notification_source_email_id(record)] if _notification_source_email_id(record) else [],
    )
    usage = _aggregate_usage_for_notification(
        usage_rows,
        notification_ids=_notification_usage_keys(record, details_obj),
        source_email_id=_notification_source_email_id(record),
    )
    
    return Notification(
        id=record.id,
        message=record.message,
        type=record.type,  # type: ignore[arg-type]
        source_email_id=record.source_email_id,
        details=details_obj,
        timestamp=record.timestamp.isoformat(),
        read=record.read,
        dismissed_at=record.dismissed_at.isoformat() if record.dismissed_at else None,
        llm_prompt_tokens=usage.get("prompt_tokens") or None,
        llm_completion_tokens=usage.get("completion_tokens") or None,
        llm_total_tokens=usage.get("total_tokens") or None,
    )


async def get_recent_notifications(
    db: AsyncSession,
    limit: int = 100,
) -> list[Notification]:
    """Return recent notifications ordered newest first."""
    result = await db.execute(
        select(NotificationRecord)
        .order_by(NotificationRecord.timestamp.desc())
        .limit(limit)
    )
    return await _enrich_notifications(db, list(result.scalars()))


async def dismiss_notification(
    db: AsyncSession,
    notification_id: str,
) -> Notification | None:
    """Mark a notification as read and return the updated record."""
    result = await db.execute(
        select(NotificationRecord).where(NotificationRecord.id == notification_id)
    )
    record = result.scalar_one_or_none()
    if record is None:
        return None

    record.read = True

    await db.commit()
    await db.refresh(record)
    details = _parse_notification_details(record)
    usage_rows = await _get_llm_usage_rows(
        db,
        _notification_usage_keys(record, details),
        [_notification_source_email_id(record)] if _notification_source_email_id(record) else [],
    )
    usage = _aggregate_usage_for_notification(
        usage_rows,
        notification_ids=_notification_usage_keys(record, details),
        source_email_id=_notification_source_email_id(record),
    )
    
    return Notification(
        id=record.id,
        message=record.message,
        type=record.type,  # type: ignore[arg-type]
        source_email_id=record.source_email_id,
        details=details,
        timestamp=record.timestamp.isoformat(),
        read=record.read,
        dismissed_at=record.dismissed_at.isoformat() if record.dismissed_at else None,
        llm_prompt_tokens=usage.get("prompt_tokens") or None,
        llm_completion_tokens=usage.get("completion_tokens") or None,
        llm_total_tokens=usage.get("total_tokens") or None,
    )


async def update_notification_message(
    db: AsyncSession,
    notification_id: str,
    message: str,
    *,
    details: dict | None = None,
) -> Notification | None:
    """Update notification message text and return updated record."""
    result = await db.execute(
        select(NotificationRecord).where(NotificationRecord.id == notification_id)
    )
    record = result.scalar_one_or_none()
    if record is None:
        return None

    record.message = message
    if details is not None:
        record.details_json = details
    await db.commit()
    await db.refresh(record)

    details = _parse_notification_details(record)
    usage_rows = await _get_llm_usage_rows(
        db,
        _notification_usage_keys(record, details),
        [_notification_source_email_id(record)] if _notification_source_email_id(record) else [],
    )
    usage = _aggregate_usage_for_notification(
        usage_rows,
        notification_ids=_notification_usage_keys(record, details),
        source_email_id=_notification_source_email_id(record),
    )
    
    return Notification(
        id=record.id,
        message=record.message,
        type=record.type,  # type: ignore[arg-type]
        source_email_id=record.source_email_id,
        details=details,
        timestamp=record.timestamp.isoformat(),
        read=record.read,
        dismissed_at=record.dismissed_at.isoformat() if record.dismissed_at else None,
        llm_prompt_tokens=usage.get("prompt_tokens") or None,
        llm_completion_tokens=usage.get("completion_tokens") or None,
        llm_total_tokens=usage.get("total_tokens") or None,
    )


async def push_notification(notification: Notification) -> None:
    """Broadcast a notification to all connected WebSocket clients."""
    await state.broadcast(
        {"type": "notification", "notification": notification.model_dump()}
    )


async def get_recent_email_summaries(db: AsyncSession, *, limit: int = 50) -> list[dict]:
    result = await db.execute(
        select(EmailItem)
        .order_by(EmailItem.received_at.desc())
        .limit(limit)
    )
    emails = result.scalars().all()
    return [
        {
            "id": email.id,
            "subject": email.subject,
            "conversation_id": email.conversation_id,
            "from": email.from_address,
            "received_at": email.received_at.isoformat(),
            "is_read": email.is_read,
            "body_preview": email.body_preview,
        }
        for email in emails
    ]
