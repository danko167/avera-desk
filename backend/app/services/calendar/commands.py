from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
import logging
import re

from sqlalchemy.ext.asyncio import AsyncSession

from ...core.runtime_config import get_llm_config
from ...integrations.email_provider import get_email_api_provider, normalize_email_provider
from ...schemas import CalendarPlanningRequest
from ..ai.usage_store import record_llm_usage
from ..email.contacts import ContactCandidate, resolve_contact_candidates
from ..interaction.client_feedback import ClientInteractionOutcome
from ..shared.outcome import ServiceExecutionOutcome
from ..shared.preferences import get_settings
from .parser import ParsedCalendarAction, parse_calendar_user_action
from . import planner

logger = logging.getLogger(__name__)

_MEETING_INTENT_RE = re.compile(
    r"\b(make|create|schedule|book|set up|arrange|plan)\b.*\b(meeting|call|appointment|calendar|invite)\b",
    re.IGNORECASE,
)
_WITH_CLAUSE_RE = re.compile(
    r"\bwith\s+(?P<attendee>.+?)(?:\s+for\s+|\s+at\s+|\s+tomorrow\b|\s+today\b|\s+next\s+|\s+on\s+|$)",
    re.IGNORECASE,
)
_DURATION_RE = re.compile(r"\bfor\s+(?P<minutes>\d{1,3})\s*(?:minutes?|mins?|m)\b", re.IGNORECASE)
_TIME_RE = re.compile(
    r"\b(?:at\s+)?(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<ampm>a\.?m\.?|p\.?m\.?)?\b",
    re.IGNORECASE,
)
_EXPLICIT_TIME_RE = re.compile(
    r"\b(?:at\s+)?\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)\b|\b\d{1,2}:\d{2}\b|\bnoon\b|\bmidnight\b",
    re.IGNORECASE,
)
_FLEXIBLE_TIME_WINDOW_RE = re.compile(r"\b(morning|afternoon|evening|tonight)\b", re.IGNORECASE)
_EMAIL_ADDRESS_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_WEEKDAY_NAMES = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


@dataclass(slots=True)
class ParsedCalendarCommand:
    title: str
    desired_start_at: datetime
    duration_minutes: int
    attendees: list[str]


@dataclass(slots=True)
class CalendarAttendeeResolution:
    emails: list[str]
    suggestions: list[dict]


def _extract_attendee_query(utterance: str) -> str | None:
    match = _WITH_CLAUSE_RE.search(utterance or "")
    if not match:
        return None
    candidate = re.sub(r"\s+", " ", match.group("attendee")).strip(" ,.;:-")
    return candidate or None


def _extract_duration_minutes(utterance: str) -> int:
    match = _DURATION_RE.search(utterance or "")
    if not match:
        return 30
    return max(15, min(480, int(match.group("minutes"))))


def _resolve_day_reference(utterance: str, *, now: datetime) -> datetime | None:
    lowered = (utterance or "").lower()
    if "tomorrow" in lowered:
        return now + timedelta(days=1)
    if "today" in lowered:
        return now

    for name, weekday in _WEEKDAY_NAMES.items():
        if f"next {name}" in lowered:
            days_ahead = ((weekday - now.weekday()) % 7) or 7
            return now + timedelta(days=days_ahead)
        if re.search(rf"\b{name}\b", lowered):
            days_ahead = (weekday - now.weekday()) % 7
            return now + timedelta(days=days_ahead)
    return None


def _resolve_time_reference(utterance: str) -> time | None:
    match = _TIME_RE.search(utterance or "")
    if not match:
        return None

    hour = int(match.group("hour"))
    minute = int(match.group("minute") or 0)
    ampm = (match.group("ampm") or "").lower().replace(".", "")

    if ampm == "pm" and hour < 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0

    if hour > 23 or minute > 59:
        return None
    return time(hour=hour, minute=minute)


def _build_title(attendee_query: str | None) -> str:
    if attendee_query:
        return f"Meeting with {attendee_query}"
    return "Meeting"


def _extract_attendee_emails_from_utterance(utterance: str) -> list[str]:
    emails: list[str] = []
    seen: set[str] = set()
    for match in _EMAIL_ADDRESS_RE.findall(utterance or ""):
        email = match.strip().lower()
        if email and email not in seen:
            seen.add(email)
            emails.append(email)
    return emails


def _should_auto_shift_for_flexible_time(utterance: str) -> bool:
    text = utterance or ""
    if not _FLEXIBLE_TIME_WINDOW_RE.search(text):
        return False
    return not _EXPLICIT_TIME_RE.search(text)


def _parse_calendar_command(utterance: str, *, now: datetime) -> ParsedCalendarCommand | None:
    if not _MEETING_INTENT_RE.search(utterance or ""):
        return None

    day_ref = _resolve_day_reference(utterance, now=now)
    time_ref = _resolve_time_reference(utterance)
    if day_ref is None or time_ref is None:
        return None

    attendee_query = _extract_attendee_query(utterance)
    local_now = now.astimezone()
    desired_start_at = datetime.combine(
        day_ref.date(),
        time_ref,
        tzinfo=local_now.tzinfo,
    )
    if desired_start_at <= local_now:
        desired_start_at = desired_start_at + timedelta(days=1)

    return ParsedCalendarCommand(
        title=_build_title(attendee_query),
        desired_start_at=desired_start_at,
        duration_minutes=_extract_duration_minutes(utterance),
        attendees=[attendee_query] if attendee_query else [],
    )


async def _resolve_attendee_emails(db: AsyncSession, attendees: list[str]) -> CalendarAttendeeResolution:
    resolved: list[str] = []
    seen: set[str] = set()
    suggestion_seen: set[str] = set()
    suggestions: list[dict] = []

    def _pick_candidate(candidates: list[ContactCandidate]) -> ContactCandidate | None:
        # Keep parity with email flow: auto-pick only when there is exactly one
        # sufficiently confident contact candidate.
        if len(candidates) == 1 and candidates[0].confidence >= 0.7:
            return candidates[0]
        return None

    def _append_suggestions(candidates: list[ContactCandidate]) -> None:
        for candidate in candidates:
            if candidate.email in suggestion_seen:
                continue
            suggestion_seen.add(candidate.email)
            suggestions.append(
                {
                    "email": candidate.email,
                    "label": candidate.label,
                    "confidence": candidate.confidence,
                    "source": candidate.source,
                }
            )

    for attendee in attendees:
        candidates = await resolve_contact_candidates(db, raw_query=attendee)
        selected = _pick_candidate(candidates)

        if selected is None:
            # Reuse email-style fuzzy recovery: retry shorter name fragments when ASR adds noise.
            tokens = sorted(
                [token for token in re.split(r"\s+", attendee.strip()) if len(token) >= 3],
                key=lambda token: len(token),
                reverse=True,
            )
            fallback_candidates: list[ContactCandidate] = candidates
            for token in tokens:
                token_candidates = await resolve_contact_candidates(db, raw_query=token)
                selected = _pick_candidate(token_candidates)
                if selected is not None:
                    break
                if token_candidates and not fallback_candidates:
                    fallback_candidates = token_candidates

            if selected is None:
                _append_suggestions(fallback_candidates)

        if selected is not None and selected.email not in seen:
            seen.add(selected.email)
            resolved.append(selected.email)
    return CalendarAttendeeResolution(emails=resolved, suggestions=suggestions)


async def _get_calendar_provider(db: AsyncSession):
    settings = await get_settings(db)
    provider_name = normalize_email_provider(settings.get("email_provider"))
    if provider_name != "m365":
        return None

    provider = get_email_api_provider(provider_name)
    if not hasattr(provider, "get_upcoming_events") or not hasattr(provider, "get_availability"):
        return None
    return provider


def _command_from_parsed_action(parsed: ParsedCalendarAction) -> ParsedCalendarCommand | None:
    if parsed.action != "create_event" or parsed.desired_start_at is None:
        return None

    attendee_queries = [item for item in parsed.attendee_queries if item]
    title = parsed.title.strip() or _build_title(attendee_queries[0] if attendee_queries else None)
    return ParsedCalendarCommand(
        title=title,
        desired_start_at=parsed.desired_start_at,
        duration_minutes=parsed.duration_minutes or 30,
        attendees=attendee_queries,
    )


async def handle_calendar_command_from_transcript(
    db: AsyncSession,
    *,
    notification_id: str | None,
    transcript_text: str,
    correlation_id: str | None = None,
) -> ServiceExecutionOutcome:
    llm_config = await get_llm_config(db)
    parse_failed = False
    parsed_action: ParsedCalendarAction
    try:
        parsed_action = await parse_calendar_user_action(db, transcript_text)
    except Exception as exc:
        logger.warning(
            "calendar_parser failed, falling back to deterministic parse error=%s utterance=%r",
            exc,
            transcript_text.encode("cp1252", errors="replace").decode("cp1252"),
        )
        parse_failed = True
        parsed_action = ParsedCalendarAction(
            action="none",
            title="",
            attendee_queries=[],
            desired_start_at=None,
            duration_minutes=None,
            reasoning=f"parse_error:{type(exc).__name__}",
        )

    if parsed_action.usage is not None:
        await record_llm_usage(
            db,
            interaction_kind="calendar_command_parse",
            provider=llm_config.provider,
            model=llm_config.model or "gpt-5.4-mini",
            usage=parsed_action.usage,
            notification_id=notification_id,
            metadata_json={"correlation_id": correlation_id, "reasoning": parsed_action.reasoning},
        )

    parsed = _command_from_parsed_action(parsed_action)
    if parsed is None and parse_failed:
        parsed = _parse_calendar_command(
            transcript_text,
            now=datetime.now().astimezone(),
        )
    if parsed is None:
        return ServiceExecutionOutcome()

    provider = await _get_calendar_provider(db)
    if provider is None:
        return ServiceExecutionOutcome(
            result="calendar_unavailable",
            display_text="Calendar commands are currently available only with Microsoft 365.",
        )

    inferred_attendees = list(parsed.attendees)
    for email in _extract_attendee_emails_from_utterance(transcript_text):
        if email not in inferred_attendees:
            inferred_attendees.append(email)

    attendee_resolution = await _resolve_attendee_emails(db, inferred_attendees)
    payload = CalendarPlanningRequest(
        action="create_event",
        title=parsed.title,
        desired_start_at=parsed.desired_start_at.isoformat(),
        duration_minutes=parsed.duration_minutes,
        timezone_name=(parsed.desired_start_at.tzname() or "UTC"),
        attendees=attendee_resolution.emails,
        source_notification_id=notification_id,
        notes=None,
        auto_shift_conflict_free_for_flexible_time=_should_auto_shift_for_flexible_time(transcript_text),
    )
    await planner.plan_calendar_proposal(
        db,
        provider=provider,
        payload=payload,
        attendee_suggestions=attendee_resolution.suggestions,
    )
    attendee_label = parsed.attendees[0] if parsed.attendees else "your calendar"
    return ServiceExecutionOutcome(
        result="calendar_proposal_ready",
        display_text=f"Meeting plan prepared for {attendee_label}. Review the proposal and approve or edit it.",
        interaction=ClientInteractionOutcome(
            dismiss_notification_id=notification_id,
            close_window=False,
        ),
    )