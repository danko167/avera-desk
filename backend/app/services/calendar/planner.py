from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import ceil, floor

from sqlalchemy.ext.asyncio import AsyncSession

from ...schemas import (
    CalendarPlanningRequest,
    CalendarPlanningResultDto,
    CalendarProposalConflictDto,
    CalendarProposalOptionDto,
)
from ..shared import notifications
from ..shared.notification_content import (
    build_calendar_proposal_notification_details,
    build_calendar_proposal_notification_message,
)
from . import proposals


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


def _to_iso(dt: datetime) -> str:
    return _as_utc(dt).isoformat()


def _overlaps(start_a: datetime, end_a: datetime, start_b: datetime, end_b: datetime) -> bool:
    return start_a < end_b and start_b < end_a


def _availability_slot_free(
    availability_view: str,
    *,
    window_start: datetime,
    slot_start: datetime,
    slot_end: datetime,
    interval_minutes: int,
) -> bool:
    if not availability_view:
        return True

    unit_seconds = interval_minutes * 60
    offset_start = max(0.0, (slot_start - window_start).total_seconds())
    offset_end = max(0.0, (slot_end - window_start).total_seconds())

    start_index = floor(offset_start / unit_seconds)
    end_index = ceil(offset_end / unit_seconds)
    end_index = min(end_index, len(availability_view))

    for index in range(start_index, end_index):
        if index < 0 or index >= len(availability_view):
            continue
        # Graph availabilityView convention: 0=free, non-zero means blocked in some form.
        if availability_view[index] != "0":
            return False

    return True


def _build_conflicts_from_events(
    events: list[dict],
    *,
    desired_start_at: datetime,
    desired_end_at: datetime,
) -> list[CalendarProposalConflictDto]:
    conflicts: list[CalendarProposalConflictDto] = []
    for event in events:
        event_start_raw = event.get("start_at")
        event_end_raw = event.get("end_at")
        if not event_start_raw or not event_end_raw:
            continue

        try:
            event_start = _parse_iso_datetime(str(event_start_raw))
            event_end = _parse_iso_datetime(str(event_end_raw))
        except ValueError:
            continue

        if not _overlaps(desired_start_at, desired_end_at, event_start, event_end):
            continue

        conflicts.append(
            CalendarProposalConflictDto(
                event_id=event.get("id"),
                title=str(event.get("subject") or "Busy event"),
                start_at=_to_iso(event_start),
                end_at=_to_iso(event_end),
                reason="Conflicts with your current calendar",
            )
        )

    return conflicts


def _build_conflicts_from_attendee_busy_items(
    availability_rows: list[dict],
    *,
    desired_start_at: datetime,
    desired_end_at: datetime,
) -> list[CalendarProposalConflictDto]:
    conflicts: list[CalendarProposalConflictDto] = []

    for attendee_row in availability_rows:
        email = str(attendee_row.get("email") or "unknown attendee")
        for item in attendee_row.get("items", []) or []:
            start_raw = item.get("start_at")
            end_raw = item.get("end_at")
            if not start_raw or not end_raw:
                continue

            try:
                busy_start = _parse_iso_datetime(str(start_raw))
                busy_end = _parse_iso_datetime(str(end_raw))
            except ValueError:
                continue

            if not _overlaps(desired_start_at, desired_end_at, busy_start, busy_end):
                continue

            conflicts.append(
                CalendarProposalConflictDto(
                    event_id=None,
                    title=str(item.get("subject") or f"Busy: {email}"),
                    start_at=_to_iso(busy_start),
                    end_at=_to_iso(busy_end),
                    reason=f"Attendee unavailable: {email}",
                )
            )

    return conflicts


def _generate_time_options(
    *,
    desired_start_at: datetime,
    duration: timedelta,
    interval_minutes: int,
    search_window_hours: int,
    availability_rows: list[dict],
    own_events: list[dict],
    max_options: int = 3,
) -> list[CalendarProposalOptionDto]:
    options: list[CalendarProposalOptionDto] = []
    scan_start = desired_start_at
    scan_end = desired_start_at + timedelta(hours=search_window_hours)

    own_busy_blocks: list[tuple[datetime, datetime]] = []
    for event in own_events:
        start_raw = event.get("start_at")
        end_raw = event.get("end_at")
        if not start_raw or not end_raw:
            continue
        try:
            own_busy_blocks.append((_parse_iso_datetime(str(start_raw)), _parse_iso_datetime(str(end_raw))))
        except ValueError:
            continue

    candidate = scan_start
    step = timedelta(minutes=interval_minutes)
    while candidate + duration <= scan_end and len(options) < max_options:
        candidate_end = candidate + duration

        own_conflict = any(
            _overlaps(candidate, candidate_end, busy_start, busy_end)
            for busy_start, busy_end in own_busy_blocks
        )
        if own_conflict:
            candidate = candidate + step
            continue

        attendee_conflict = False
        for attendee_row in availability_rows:
            if not _availability_slot_free(
                str(attendee_row.get("availability_view") or ""),
                window_start=scan_start,
                slot_start=candidate,
                slot_end=candidate_end,
                interval_minutes=interval_minutes,
            ):
                attendee_conflict = True
                break

        if attendee_conflict:
            candidate = candidate + step
            continue

        reason = "Requested slot is available" if candidate == desired_start_at else "Suggested conflict-free alternative"
        confidence = 0.95 if candidate == desired_start_at else max(0.5, 0.8 - (0.1 * len(options)))
        options.append(
            CalendarProposalOptionDto(
                start_at=_to_iso(candidate),
                end_at=_to_iso(candidate_end),
                reason=reason,
                confidence=confidence,
            )
        )
        candidate = candidate + step

    return options


async def plan_calendar_proposal(
    db: AsyncSession,
    *,
    provider,
    payload: CalendarPlanningRequest,
    attendee_suggestions: list[dict] | None = None,
) -> CalendarPlanningResultDto:
    desired_start_at = _parse_iso_datetime(payload.desired_start_at)
    if payload.desired_end_at:
        desired_end_at = _parse_iso_datetime(payload.desired_end_at)
    else:
        desired_end_at = desired_start_at + timedelta(minutes=payload.duration_minutes)

    if desired_end_at <= desired_start_at:
        raise ValueError("desired_end_at must be after desired_start_at")

    duration = desired_end_at - desired_start_at

    own_events = await provider.get_upcoming_events(
        db,
        start_at=desired_start_at,
        end_at=desired_start_at + timedelta(hours=payload.search_window_hours),
        limit=100,
    )

    availability_rows = await provider.get_availability(
        db,
        attendees=payload.attendees,
        start_at=desired_start_at,
        end_at=desired_start_at + timedelta(hours=payload.search_window_hours),
        interval_minutes=payload.interval_minutes,
    )

    conflicts = _build_conflicts_from_events(
        own_events,
        desired_start_at=desired_start_at,
        desired_end_at=desired_end_at,
    )
    conflicts.extend(
        _build_conflicts_from_attendee_busy_items(
            availability_rows,
            desired_start_at=desired_start_at,
            desired_end_at=desired_end_at,
        )
    )

    options = _generate_time_options(
        desired_start_at=desired_start_at,
        duration=duration,
        interval_minutes=payload.interval_minutes,
        search_window_hours=payload.search_window_hours,
        availability_rows=availability_rows,
        own_events=own_events,
    )

    auto_shifted = False
    if payload.auto_shift_conflict_free_for_flexible_time and conflicts and options:
        shifted_start = _parse_iso_datetime(options[0].start_at)
        shifted_end = _parse_iso_datetime(options[0].end_at)

        desired_start_at = shifted_start
        desired_end_at = shifted_end
        duration = desired_end_at - desired_start_at
        auto_shifted = True

        conflicts = _build_conflicts_from_events(
            own_events,
            desired_start_at=desired_start_at,
            desired_end_at=desired_end_at,
        )
        conflicts.extend(
            _build_conflicts_from_attendee_busy_items(
                availability_rows,
                desired_start_at=desired_start_at,
                desired_end_at=desired_end_at,
            )
        )

        options = _generate_time_options(
            desired_start_at=desired_start_at,
            duration=duration,
            interval_minutes=payload.interval_minutes,
            search_window_hours=payload.search_window_hours,
            availability_rows=availability_rows,
            own_events=own_events,
        )

    if auto_shifted and not conflicts:
        reasoning = "Requested flexible time had conflicts; moved to the nearest conflict-free slot."
    elif auto_shifted and conflicts:
        reasoning = (
            f"Requested flexible time had conflicts; shifted to nearest slot but still found {len(conflicts)} conflict(s)."
        )
    else:
        reasoning = (
            "Found no conflicts for requested slot."
            if not conflicts
            else f"Found {len(conflicts)} conflict(s); proposed {len(options)} alternative option(s)."
        )

    proposal = await proposals.create_proposal(
        db,
        provider="m365",
        action=payload.action,
        title=payload.title,
        start_at=_to_iso(desired_start_at),
        end_at=_to_iso(desired_end_at),
        timezone_name=payload.timezone_name,
        attendees=payload.attendees,
        target_event_id=payload.target_event_id,
        source_email_id=payload.source_email_id,
        source_followup_id=payload.source_followup_id,
        source_notification_id=payload.source_notification_id,
        conflicts=conflicts,
        options=options,
        attendee_suggestions=attendee_suggestions,
        notes=payload.notes,
    )

    message = build_calendar_proposal_notification_message(
        proposal_id=proposal.id,
        title=proposal.title,
        action=proposal.action,
        status=proposal.status,
    )
    notification_type = "warning" if conflicts else "info"
    proposal_notification = await notifications.create_notification(
        db,
        message,
        notification_type,
        source_email_id=payload.source_email_id,
        details=build_calendar_proposal_notification_details(
            title=proposal.title,
            action=proposal.action,
            status=proposal.status,
            conflict_count=len(conflicts),
            option_count=len(options),
            source_notification_id=payload.source_notification_id,
        ),
    )
    await notifications.push_notification(proposal_notification)
    attached = await proposals.attach_source_notification(
        db,
        proposal_id=proposal.id,
        notification_id=proposal_notification.id,
    )
    if attached is not None:
        proposal = attached

    return CalendarPlanningResultDto(
        proposal=proposal,
        conflicts=conflicts,
        options=options,
        reasoning=reasoning,
    )
