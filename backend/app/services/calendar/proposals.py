from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...integrations.email_provider import get_email_api_provider, normalize_email_provider
from ...db.tables import CalendarProposalRecord
from ..shared import preferences
from ..shared import notifications
from ..shared.notification_content import (
    build_calendar_proposal_notification_details,
    build_calendar_proposal_notification_message,
)
from ...schemas import (
    CalendarAttendeeSuggestionDto,
    CalendarProposalConflictDto,
    CalendarProposalDto,
    CalendarProposalOptionDto,
    CalendarProposalStatus,
)

_EDITABLE_STATUSES: set[str] = {"proposed", "awaiting_user_decision"}


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_iso_datetime(value: str) -> datetime:
    raw = value.strip()
    if not raw:
        raise ValueError("Datetime cannot be empty")
    normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    parsed = datetime.fromisoformat(normalized)
    return _as_utc(parsed)


def _normalize_attendees(attendees: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for attendee in attendees:
        email = attendee.strip().lower()
        if not email or email in seen:
            continue
        seen.add(email)
        normalized.append(email)
    return normalized


def _json_list(items: list[Any]) -> dict[str, Any]:
    return {"items": items}


async def _get_calendar_provider(db: AsyncSession):
    settings = await preferences.get_settings(db)
    provider_name = normalize_email_provider(settings.get("email_provider"))
    provider = get_email_api_provider(provider_name)
    create_event = getattr(provider, "create_calendar_event", None)
    if not callable(create_event):
        return None
    return provider


def _proposal_notification_message(record: CalendarProposalRecord) -> str:
    return build_calendar_proposal_notification_message(
        proposal_id=record.id,
        title=record.title,
        action=record.action,
        status=record.status,
    )


def _proposal_notification_details(record: CalendarProposalRecord) -> dict:
    conflicts = record.conflicts_json.get("items", []) if isinstance(record.conflicts_json, dict) else []
    options = record.options_json.get("items", []) if isinstance(record.options_json, dict) else []
    return build_calendar_proposal_notification_details(
        title=record.title,
        action=record.action,
        status=record.status,
        conflict_count=len(conflicts),
        option_count=len(options),
    )


async def _sync_proposal_notification(db: AsyncSession, record: CalendarProposalRecord) -> None:
    notification_id = (record.source_notification_id or "").strip()
    if not notification_id:
        return

    updated = await notifications.update_notification_message(
        db,
        notification_id,
        _proposal_notification_message(record),
        details=_proposal_notification_details(record),
    )
    if updated is not None:
        await notifications.push_notification(updated)


def _to_dto(record: CalendarProposalRecord) -> CalendarProposalDto:
    attendees = record.attendees_json.get("items", []) if isinstance(record.attendees_json, dict) else []
    conflicts = record.conflicts_json.get("items", []) if isinstance(record.conflicts_json, dict) else []
    options = record.options_json.get("items", []) if isinstance(record.options_json, dict) else []

    mapped_conflicts = [
        CalendarProposalConflictDto(
            event_id=item.get("event_id"),
            title=str(item.get("title") or ""),
            start_at=str(item.get("start_at") or ""),
            end_at=str(item.get("end_at") or ""),
            reason=item.get("reason"),
        )
        for item in conflicts
        if item.get("title") and item.get("start_at") and item.get("end_at")
    ]

    mapped_options = [
        CalendarProposalOptionDto(
            start_at=str(item.get("start_at") or ""),
            end_at=str(item.get("end_at") or ""),
            reason=item.get("reason"),
            confidence=float(item.get("confidence") or 0.0),
        )
        for item in options
        if item.get("start_at") and item.get("end_at")
    ]

    metadata = record.metadata_json if isinstance(record.metadata_json, dict) else {}
    raw_attendee_suggestions = metadata.get("attendee_suggestions", []) if isinstance(metadata, dict) else []
    mapped_attendee_suggestions = [
        CalendarAttendeeSuggestionDto(
            email=str(item.get("email") or ""),
            label=(item.get("label") or None),
            confidence=float(item.get("confidence") or 0.0),
            source=(item.get("source") or None),
        )
        for item in raw_attendee_suggestions
        if isinstance(item, dict) and item.get("email")
    ]

    return CalendarProposalDto(
        id=record.id,
        provider=record.provider,  # type: ignore[arg-type]
        action=record.action,  # type: ignore[arg-type]
        status=record.status,  # type: ignore[arg-type]
        title=record.title,
        start_at=_as_utc(record.start_at).isoformat(),
        end_at=_as_utc(record.end_at).isoformat(),
        timezone_name=record.timezone_name,
        attendees=[str(value) for value in attendees if isinstance(value, str)],
        target_event_id=record.target_event_id,
        source_email_id=record.source_email_id,
        source_followup_id=record.source_followup_id,
        source_notification_id=record.source_notification_id,
        conflicts=mapped_conflicts,
        options=mapped_options,
        attendee_suggestions=mapped_attendee_suggestions,
        notes=record.notes,
        created_at=_as_utc(record.created_at).isoformat(),
        updated_at=_as_utc(record.updated_at).isoformat(),
        approved_at=_as_utc(record.approved_at).isoformat() if record.approved_at else None,
        rejected_at=_as_utc(record.rejected_at).isoformat() if record.rejected_at else None,
    )


async def _get_record(db: AsyncSession, proposal_id: str) -> CalendarProposalRecord | None:
    result = await db.execute(select(CalendarProposalRecord).where(CalendarProposalRecord.id == proposal_id))
    return result.scalar_one_or_none()


async def list_proposals(
    db: AsyncSession,
    *,
    status: CalendarProposalStatus | None,
    limit: int,
) -> list[CalendarProposalDto]:
    query = select(CalendarProposalRecord).order_by(CalendarProposalRecord.created_at.desc()).limit(limit)
    if status is not None:
        query = query.where(CalendarProposalRecord.status == status)

    result = await db.execute(query)
    records = result.scalars().all()
    return [_to_dto(record) for record in records]


async def get_proposal_by_id(db: AsyncSession, proposal_id: str) -> CalendarProposalDto | None:
    record = await _get_record(db, proposal_id)
    if record is None:
        return None
    return _to_dto(record)


async def attach_source_notification(
    db: AsyncSession,
    *,
    proposal_id: str,
    notification_id: str,
) -> CalendarProposalDto | None:
    record = await _get_record(db, proposal_id)
    if record is None:
        return None

    cleaned = notification_id.strip()
    record.source_notification_id = cleaned or None
    record.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(record)
    return _to_dto(record)


async def create_proposal(
    db: AsyncSession,
    *,
    provider: str,
    action: str,
    title: str,
    start_at: str,
    end_at: str,
    timezone_name: str,
    attendees: list[str],
    target_event_id: str | None,
    source_email_id: str | None,
    source_followup_id: str | None,
    source_notification_id: str | None,
    conflicts: list[CalendarProposalConflictDto],
    options: list[CalendarProposalOptionDto],
    attendee_suggestions: list[dict] | None,
    notes: str | None,
) -> CalendarProposalDto:
    parsed_start_at = _parse_iso_datetime(start_at)
    parsed_end_at = _parse_iso_datetime(end_at)
    if parsed_end_at <= parsed_start_at:
        raise ValueError("end_at must be after start_at")

    now = datetime.now(timezone.utc)
    record = CalendarProposalRecord(
        id=str(uuid.uuid4()),
        provider=provider,
        action=action,
        status="awaiting_user_decision",
        title=title.strip(),
        start_at=parsed_start_at,
        end_at=parsed_end_at,
        timezone_name=timezone_name.strip() or "UTC",
        attendees_json=_json_list(_normalize_attendees(attendees)),
        target_event_id=target_event_id.strip() if target_event_id else None,
        source_email_id=source_email_id.strip() if source_email_id else None,
        source_followup_id=source_followup_id.strip() if source_followup_id else None,
        source_notification_id=source_notification_id.strip() if source_notification_id else None,
        conflicts_json=_json_list([item.model_dump() for item in conflicts]),
        options_json=_json_list([item.model_dump() for item in options]),
        notes=notes.strip() if notes else None,
        metadata_json={
            "execution": "manual_only",
            "attendee_suggestions": attendee_suggestions or [],
        },
        created_at=now,
        updated_at=now,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    await _sync_proposal_notification(db, record)
    return _to_dto(record)


async def update_proposal(
    db: AsyncSession,
    *,
    proposal_id: str,
    title: str | None,
    start_at: str | None,
    end_at: str | None,
    timezone_name: str | None,
    attendees: list[str] | None,
    target_event_id: str | None,
    conflicts: list[CalendarProposalConflictDto] | None,
    options: list[CalendarProposalOptionDto] | None,
    notes: str | None,
) -> CalendarProposalDto | None:
    record = await _get_record(db, proposal_id)
    if record is None or record.status not in _EDITABLE_STATUSES:
        return None

    next_start_at = _as_utc(record.start_at)
    next_end_at = _as_utc(record.end_at)
    if start_at is not None:
        next_start_at = _parse_iso_datetime(start_at)
    if end_at is not None:
        next_end_at = _parse_iso_datetime(end_at)
    if next_end_at <= next_start_at:
        raise ValueError("end_at must be after start_at")

    if title is not None:
        record.title = title.strip()
    if timezone_name is not None:
        record.timezone_name = timezone_name.strip() or "UTC"
    if attendees is not None:
        record.attendees_json = _json_list(_normalize_attendees(attendees))
    if target_event_id is not None:
        cleaned = target_event_id.strip()
        record.target_event_id = cleaned or None
    if conflicts is not None:
        record.conflicts_json = _json_list([item.model_dump() for item in conflicts])
    if options is not None:
        record.options_json = _json_list([item.model_dump() for item in options])
    if notes is not None:
        cleaned_notes = notes.strip()
        record.notes = cleaned_notes or None

    record.start_at = next_start_at
    record.end_at = next_end_at
    record.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(record)
    await _sync_proposal_notification(db, record)
    return _to_dto(record)


async def approve_proposal(db: AsyncSession, *, proposal_id: str) -> CalendarProposalDto | None:
    record = await _get_record(db, proposal_id)
    if record is None or record.status not in _EDITABLE_STATUSES:
        return None

    event_payload: dict | None = None
    if record.action == "create_event":
        provider = await _get_calendar_provider(db)
        if provider is None:
            raise RuntimeError("Calendar event creation is not available for this provider.")

        attendees = record.attendees_json.get("items", []) if isinstance(record.attendees_json, dict) else []
        event_payload = await provider.create_calendar_event(
            db,
            subject=record.title,
            start_at=_as_utc(record.start_at),
            end_at=_as_utc(record.end_at),
            attendees=[str(value) for value in attendees if isinstance(value, str)],
            timezone_name=record.timezone_name,
            body_text=record.notes or None,
        )
        if event_payload is None:
            raise RuntimeError("Failed to create the calendar event.")

    now = datetime.now(timezone.utc)
    record.status = "approved"
    record.approved_at = now
    record.rejected_at = None
    record.updated_at = now

    if event_payload is not None:
        event_id = str(event_payload.get("id") or "").strip()
        if event_id:
            record.target_event_id = event_id

    metadata = dict(record.metadata_json or {})
    metadata["approved_without_auto_execution"] = event_payload is None
    if event_payload is not None:
        metadata["execution"] = "calendar_event_created"
    record.metadata_json = metadata

    await db.commit()
    await db.refresh(record)
    await _sync_proposal_notification(db, record)
    return _to_dto(record)


async def reject_proposal(
    db: AsyncSession,
    *,
    proposal_id: str,
    reason: str | None,
) -> CalendarProposalDto | None:
    record = await _get_record(db, proposal_id)
    if record is None or record.status not in _EDITABLE_STATUSES:
        return None

    now = datetime.now(timezone.utc)
    record.status = "rejected"
    record.rejected_at = now
    record.approved_at = None
    record.updated_at = now

    metadata = dict(record.metadata_json or {})
    metadata["rejection_reason"] = (reason or "").strip() or None
    record.metadata_json = metadata

    await db.commit()
    await db.refresh(record)
    return _to_dto(record)


async def cancel_proposal(db: AsyncSession, *, proposal_id: str) -> CalendarProposalDto | None:
    record = await _get_record(db, proposal_id)
    if record is None:
        return None

    if record.status in {"approved", "rejected", "canceled"}:
        return _to_dto(record)

    record.status = "canceled"
    record.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(record)
    await _sync_proposal_notification(db, record)
    return _to_dto(record)
