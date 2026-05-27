from __future__ import annotations

from datetime import datetime, timezone
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.tables import EmailDraftRecord
from ...integrations.email_provider import get_email_api_provider, normalize_email_provider
from ...schemas import EmailDraftDto, EmailDraftSuggestionDto
from ..shared.notification_content import (
    build_email_draft_notification_details,
    build_email_draft_notification_message,
)
from ..shared import notifications
from ..shared.preferences import get_settings


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _to_dto(record: EmailDraftRecord) -> EmailDraftDto:
    suggestions = record.suggestions_json.get("candidates", []) if isinstance(record.suggestions_json, dict) else []
    mapped = [
        EmailDraftSuggestionDto(
            email=str(item.get("email") or ""),
            label=(item.get("label") or None),
            confidence=float(item.get("confidence") or 0.0),
        )
        for item in suggestions
        if item.get("email")
    ]

    return EmailDraftDto(
        id=record.id,
        mode=record.mode,  # type: ignore[arg-type]
        status=record.status,  # type: ignore[arg-type]
        recipient_email=record.recipient_email,
        subject=record.subject,
        body=record.body,
        source_email_id=record.source_email_id,
        source_notification_id=record.source_notification_id,
        send_notification_id=record.send_notification_id,
        suggestions=mapped,
        created_at=_as_utc(record.created_at).isoformat(),
        updated_at=_as_utc(record.updated_at).isoformat(),
        sent_at=_as_utc(record.sent_at).isoformat() if record.sent_at else None,
    )


def _draft_notification_message(record: EmailDraftRecord) -> str:
    return build_email_draft_notification_message(
        draft_id=record.id,
        recipient_email=record.recipient_email,
    )


def _draft_notification_details(record: EmailDraftRecord) -> dict:
    return build_email_draft_notification_details(
        recipient_email=record.recipient_email,
        source_notification_id=record.source_notification_id,
    )


async def _sync_draft_notification(db: AsyncSession, record: EmailDraftRecord) -> None:
    notification_id = (record.send_notification_id or "").strip()
    if not notification_id:
        return

    updated = await notifications.update_notification_message(
        db,
        notification_id,
        _draft_notification_message(record),
        details=_draft_notification_details(record),
    )
    if updated is not None:
        await notifications.push_notification(updated)


def _linked_notification_ids(record: EmailDraftRecord) -> list[str]:
    ids: list[str] = []
    for candidate in (record.send_notification_id, record.source_notification_id):
        cleaned = (candidate or "").strip()
        if cleaned and cleaned not in ids:
            ids.append(cleaned)
    return ids


async def _dismiss_linked_notification(db: AsyncSession, record: EmailDraftRecord) -> None:
    for notification_id in _linked_notification_ids(record):
        dismissed = await notifications.dismiss_notification(db, notification_id)
        if dismissed is not None:
            await notifications.push_notification(dismissed)
            return


async def create_draft(
    db: AsyncSession,
    *,
    mode: str,
    recipient_email: str | None,
    subject: str,
    body: str,
    source_email_id: str | None,
    source_notification_id: str | None,
    suggestions: list[dict] | None = None,
    metadata: dict | None = None,
) -> EmailDraftDto:
    now = datetime.now(timezone.utc)
    record = EmailDraftRecord(
        id=str(uuid.uuid4()),
        mode=mode,
        status="pending",
        recipient_email=recipient_email,
        subject=subject,
        body=body,
        source_email_id=source_email_id,
        source_notification_id=source_notification_id,
        suggestions_json={"candidates": suggestions or []},
        metadata_json=metadata or {},
        created_at=now,
        updated_at=now,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return _to_dto(record)


async def _get_draft_record(db: AsyncSession, draft_id: str) -> EmailDraftRecord | None:
    result = await db.execute(select(EmailDraftRecord).where(EmailDraftRecord.id == draft_id))
    return result.scalar_one_or_none()


async def get_draft_by_id(db: AsyncSession, draft_id: str) -> EmailDraftDto | None:
    record = await _get_draft_record(db, draft_id)
    if record is None:
        return None
    return _to_dto(record)


async def attach_send_notification(
    db: AsyncSession,
    *,
    draft_id: str,
    notification_id: str,
) -> EmailDraftDto | None:
    record = await _get_draft_record(db, draft_id)
    if record is None:
        return None

    record.send_notification_id = notification_id.strip() or None
    record.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(record)
    return _to_dto(record)


async def update_draft(
    db: AsyncSession,
    *,
    draft_id: str,
    recipient_email: str | None = None,
    subject: str | None = None,
    body: str | None = None,
) -> EmailDraftDto | None:
    record = await _get_draft_record(db, draft_id)
    if record is None or record.status != "pending":
        return None

    if recipient_email is not None:
        record.recipient_email = recipient_email.strip().lower() or None
    if subject is not None:
        record.subject = subject.strip()
    if body is not None:
        record.body = body.strip()
    record.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(record)
    await _sync_draft_notification(db, record)
    return _to_dto(record)


async def cancel_draft(db: AsyncSession, *, draft_id: str) -> EmailDraftDto | None:
    record = await _get_draft_record(db, draft_id)
    if record is None:
        return None

    if record.status == "pending":
        record.status = "canceled"
        record.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(record)
        await _dismiss_linked_notification(db, record)
    return _to_dto(record)


async def send_draft(db: AsyncSession, *, draft_id: str) -> EmailDraftDto | None:
    record = await _get_draft_record(db, draft_id)
    if record is None or record.status != "pending":
        return None

    recipient = (record.recipient_email or "").strip()
    if not recipient and record.mode == "new_email":
        return None

    settings = await get_settings(db)
    email_provider = normalize_email_provider(settings.get("email_provider"))
    provider = get_email_api_provider(email_provider)
    if record.mode == "reply" and record.source_email_id:
        sent = await provider.reply_to_message(
            db,
            message_id=record.source_email_id,
            body_text=record.body,
        )
    else:
        sent = await provider.send_mail(
            db,
            to_recipients=[recipient],
            subject=record.subject,
            body_text=record.body,
        )

    if not sent:
        return None

    now = datetime.now(timezone.utc)
    record.status = "sent"
    record.sent_at = now
    record.updated_at = now
    await db.commit()
    await db.refresh(record)
    await _dismiss_linked_notification(db, record)
    return _to_dto(record)
