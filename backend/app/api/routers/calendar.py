from __future__ import annotations

from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query

from ...db import db_session
from ...integrations.email_provider import get_email_api_provider, normalize_email_provider
from ...schemas import (
    CalendarAvailabilityDto,
    CalendarAvailabilityRequest,
    CalendarEventDto,
    CalendarPlanningRequest,
    CalendarPlanningResultDto,
    CalendarProposalDto,
    CalendarProposalStatus,
    CreateCalendarProposalRequest,
    RejectCalendarProposalRequest,
    UpdateCalendarProposalRequest,
)
from ...services.calendar import planner, proposals
from ...services.shared.preferences import get_settings

router = APIRouter()


def _parse_iso_datetime(value: str) -> datetime:
    raw = value.strip()
    if not raw:
        raise ValueError("Datetime cannot be empty")
    normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


async def _get_graph_provider(db):
    settings = await get_settings(db)
    provider_name = normalize_email_provider(settings.get("email_provider"))
    if provider_name != "m365":
        raise HTTPException(
            status_code=400,
            detail="Calendar endpoints are currently available only for m365 provider",
        )

    provider = get_email_api_provider(provider_name)
    if not hasattr(provider, "get_upcoming_events") or not hasattr(provider, "get_availability"):
        raise HTTPException(status_code=400, detail="Calendar provider methods are unavailable")
    return provider


@router.get("/calendar/events/upcoming", response_model=list[CalendarEventDto])
async def get_calendar_upcoming_events(
    start_at: str = Query(..., description="ISO datetime"),
    end_at: str = Query(..., description="ISO datetime"),
    limit: int = Query(default=25, ge=1, le=100),
) -> list[CalendarEventDto]:
    try:
        parsed_start_at = _parse_iso_datetime(start_at)
        parsed_end_at = _parse_iso_datetime(end_at)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if parsed_end_at <= parsed_start_at:
        raise HTTPException(status_code=400, detail="end_at must be after start_at")

    async with db_session() as db:
        provider = await _get_graph_provider(db)
        events = await provider.get_upcoming_events(
            db,
            start_at=parsed_start_at,
            end_at=parsed_end_at,
            limit=limit,
        )
    return [CalendarEventDto.model_validate(item) for item in events]


@router.post("/calendar/availability", response_model=list[CalendarAvailabilityDto])
async def get_calendar_availability(payload: CalendarAvailabilityRequest) -> list[CalendarAvailabilityDto]:
    try:
        parsed_start_at = _parse_iso_datetime(payload.start_at)
        parsed_end_at = _parse_iso_datetime(payload.end_at)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if parsed_end_at <= parsed_start_at:
        raise HTTPException(status_code=400, detail="end_at must be after start_at")

    async with db_session() as db:
        provider = await _get_graph_provider(db)
        availability = await provider.get_availability(
            db,
            attendees=payload.attendees,
            start_at=parsed_start_at,
            end_at=parsed_end_at,
            interval_minutes=payload.interval_minutes,
        )
    return [CalendarAvailabilityDto.model_validate(item) for item in availability]


@router.post("/calendar-proposals/plan", response_model=CalendarPlanningResultDto)
async def plan_calendar_proposal(payload: CalendarPlanningRequest) -> CalendarPlanningResultDto:
    async with db_session() as db:
        provider = await _get_graph_provider(db)
        try:
            return await planner.plan_calendar_proposal(
                db,
                provider=provider,
                payload=payload,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/calendar-proposals", response_model=list[CalendarProposalDto])
async def list_calendar_proposals(
    status: CalendarProposalStatus | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[CalendarProposalDto]:
    async with db_session() as db:
        return await proposals.list_proposals(db, status=status, limit=limit)


@router.post("/calendar-proposals", response_model=CalendarProposalDto)
async def create_calendar_proposal(payload: CreateCalendarProposalRequest) -> CalendarProposalDto:
    async with db_session() as db:
        try:
            return await proposals.create_proposal(
                db,
                provider=payload.provider,
                action=payload.action,
                title=payload.title,
                start_at=payload.start_at,
                end_at=payload.end_at,
                timezone_name=payload.timezone_name,
                attendees=payload.attendees,
                target_event_id=payload.target_event_id,
                source_email_id=payload.source_email_id,
                source_followup_id=payload.source_followup_id,
                source_notification_id=payload.source_notification_id,
                conflicts=payload.conflicts,
                options=payload.options,
                attendee_suggestions=None,
                notes=payload.notes,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/calendar-proposals/{proposal_id}", response_model=CalendarProposalDto)
async def get_calendar_proposal_by_id(proposal_id: str) -> CalendarProposalDto:
    async with db_session() as db:
        proposal = await proposals.get_proposal_by_id(db, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Calendar proposal not found")
    return proposal


@router.patch("/calendar-proposals/{proposal_id}", response_model=CalendarProposalDto)
async def patch_calendar_proposal(
    proposal_id: str,
    payload: UpdateCalendarProposalRequest,
) -> CalendarProposalDto:
    async with db_session() as db:
        try:
            proposal = await proposals.update_proposal(
                db,
                proposal_id=proposal_id,
                title=payload.title,
                start_at=payload.start_at,
                end_at=payload.end_at,
                timezone_name=payload.timezone_name,
                attendees=payload.attendees,
                target_event_id=payload.target_event_id,
                conflicts=payload.conflicts,
                options=payload.options,
                notes=payload.notes,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    if proposal is None:
        raise HTTPException(status_code=404, detail="Editable calendar proposal not found")
    return proposal


@router.post("/calendar-proposals/{proposal_id}/approve", response_model=CalendarProposalDto)
async def approve_calendar_proposal(proposal_id: str) -> CalendarProposalDto:
    async with db_session() as db:
        try:
            proposal = await proposals.approve_proposal(db, proposal_id=proposal_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    if proposal is None:
        raise HTTPException(status_code=404, detail="Pending calendar proposal not found")
    return proposal


@router.post("/calendar-proposals/{proposal_id}/reject", response_model=CalendarProposalDto)
async def reject_calendar_proposal(
    proposal_id: str,
    payload: RejectCalendarProposalRequest,
) -> CalendarProposalDto:
    async with db_session() as db:
        proposal = await proposals.reject_proposal(
            db,
            proposal_id=proposal_id,
            reason=payload.reason,
        )
    if proposal is None:
        raise HTTPException(status_code=404, detail="Pending calendar proposal not found")
    return proposal


@router.post("/calendar-proposals/{proposal_id}/cancel", response_model=CalendarProposalDto)
async def cancel_calendar_proposal(proposal_id: str) -> CalendarProposalDto:
    async with db_session() as db:
        proposal = await proposals.cancel_proposal(db, proposal_id=proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Calendar proposal not found")
    return proposal
