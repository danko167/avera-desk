from __future__ import annotations

from dataclasses import dataclass
import logging
import re
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.runtime_config import get_llm_config
from ...core.control_intent import classify_control_intent
from ...db.tables import EmailItem, FollowUpItem, NotificationRecord
from ..common.followup_markers import extract_follow_up_id
from ..interaction.client_feedback import ClientInteractionOutcome
from ..ai.usage_store import record_llm_usage
from ..shared.notification_content import (
    build_email_draft_notification_details,
    build_email_draft_notification_message,
)
from ..shared.notifications import create_notification, push_notification
from ..shared.outcome import ServiceExecutionOutcome
from .parser import ParsedEmailAction, extract_recipient_from_text, parse_email_user_action
from .contacts import resolve_contact_candidates
from .context import preprocess_email_context
from .drafting import draft_email
from . import draft_runtime

logger = logging.getLogger(__name__)
_DRAFT_GREETING_RE = re.compile(r"^(?:hi|hello|dear)\s+(.{1,80}?)[,:!]\s*$", re.IGNORECASE)
_AFFIRMATIVE_REPLY_RE = re.compile(
    r"^(?:yes|yeah|yep|sure|ok|okay|sounds good|works for me|i can do that|we can do that|i am available|i can make it|that works|confirmed)\b",
    re.IGNORECASE,
)
_REQUEST_CONTEXT_RE = re.compile(
    r"\?|\b(can\s+you|could\s+you|please|confirm|approve|meeting|meet|available|availability|tomorrow|today|schedule)\b",
    re.IGNORECASE,
)
_MEETING_CONTEXT_RE = re.compile(
    r"\b(meeting|calendar|invite|appointment|schedule|reschedule|available|availability|tomorrow|today|monday|tuesday|wednesday|thursday|friday|saturday|sunday|am|pm)\b",
    re.IGNORECASE,
)
_NEGATIVE_REPLY_RE = re.compile(
    r"^\s*(?:(?:um+|uh+|hmm+|well|ah|oh)\s+)*(?:no|nope|nah|can(?:\s*not|'t)|cannot|not\s+available|won'?t\s+work|doesn'?t\s+work|sorry\b.*\bcan(?:\s*not|'t))\b",
    re.IGNORECASE,
)
_COUNTER_REPLY_HINT_RE = re.compile(
    r"\b(but|instead|rather|how\s+about|what\s+about|day\s+after|next\s+day|tomorrow|at\s+\d{1,2}|\d{1,2}:\d{2}|am|pm|make\s+it|let'?s\s+make\s+it|lets\s+make\s+it|move\s+it\s+to)\b",
    re.IGNORECASE,
)
_DAY_REFERENCE_RE = re.compile(
    r"\b(today|tomorrow|tonight|monday|tuesday|wednesday|thursday|friday|saturday|sunday|next\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|day\s+after|next\s+day)\b",
    re.IGNORECASE,
)
_SPOKEN_COUNTER_TIME_RE = re.compile(
    r"\b(?:make\s+it|let'?s\s+make\s+it|lets\s+make\s+it|move\s+it\s+to|at)\s+"
    r"(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|noon|midnight)"
    r"(?:\s+(?:fifteen|thirty|forty\s+five))?\b",
    re.IGNORECASE,
)
_EXPLICIT_COUNTER_TIME_RE = re.compile(
    r"\b(?:at\s+)?(?:\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|noon|midnight)"
    r"(?:\s+(?:fifteen|thirty|forty\s+five))?\b",
    re.IGNORECASE,
)
_DELEGATE_INVITE_RE = re.compile(
    r"\b(send|share|forward)\s+(?:me\s+)?(?:an?\s+)?(?:calendar\s+)?invite\b|\bsend\s+over\s+(?:an?\s+)?invite\b",
    re.IGNORECASE,
)
_BARE_TEN_REPLY_RE = re.compile(
    r"\b(?:let'?s\s+make\s+it|make\s+it|move\s+it\s+to|at)\s+ten\b(?!\s*(?:a\.?m\.?|p\.?m\.?))",
    re.IGNORECASE,
)
_EXPLICIT_REQUESTED_TIME_RE = re.compile(
    r"\b(?:let'?s\s+make\s+it|make\s+it|move\s+it\s+to|at)\s+"
    r"(?P<hour>one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|\d{1,2})"
    r"(?:\s+(?P<minute>fifteen|thirty|forty\s+five|\d{2}))?"
    r"(?:\s*(?P<ampm>a\.?m\.?|p\.?m\.?)\b)?",
    re.IGNORECASE,
)
_SPOKEN_HOUR_TO_24 = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}


def _format_requested_time_hint(text: str) -> str | None:
    match = _EXPLICIT_REQUESTED_TIME_RE.search(text or "")
    if not match:
        return None

    hour_token = match.group("hour") or ""
    minute_token = (match.group("minute") or "").lower().replace(" ", "")
    ampm_token = (match.group("ampm") or "").lower().replace(".", "")

    if hour_token.isdigit():
        hour = int(hour_token)
    else:
        hour = _SPOKEN_HOUR_TO_24.get(hour_token.lower(), 0)

    if hour <= 0:
        return None

    minute = 0
    if minute_token in {"fifteen", "15"}:
        minute = 15
    elif minute_token in {"thirty", "30"}:
        minute = 30
    elif minute_token in {"fortyfive", "45"}:
        minute = 45
    elif minute_token.isdigit():
        minute = int(minute_token)

    if ampm_token == "pm" and hour < 12:
        hour += 12
    elif ampm_token == "am" and hour == 12:
        hour = 0

    if hour == 0:
        hour = 12

    suffix = "AM" if hour < 12 else "PM"
    display_hour = hour if 1 <= hour <= 12 else hour - 12
    if display_hour == 0:
        display_hour = 12

    return f"{display_hour}:{minute:02d} {suffix}"

MeetingReplyMode = Literal["accept", "decline", "counter", "none"]


@dataclass(slots=True)
class _ResolvedEmailContext:
    resolved_notification_id: str
    follow_up_id: str | None
    email_item: EmailItem | None


def _extract_follow_up_id(message: str) -> str | None:
    return extract_follow_up_id(message)


async def _load_notification(db: AsyncSession, notification_id: str) -> NotificationRecord | None:
    result = await db.execute(
        select(NotificationRecord).where(NotificationRecord.id == notification_id)
    )
    return result.scalar_one_or_none()


async def _resolve_context(db: AsyncSession, *, notification_id: str | None) -> _ResolvedEmailContext | None:
    notification: NotificationRecord | None = None
    if notification_id:
        notification = await _load_notification(db, notification_id)

    if notification is None:
        recent_result = await db.execute(
            select(NotificationRecord)
            .where(NotificationRecord.read.is_(False))
            .order_by(NotificationRecord.timestamp.desc())
            .limit(25)
        )
        for candidate in recent_result.scalars().all():
            if _extract_follow_up_id(candidate.message):
                notification = candidate
                break

    if notification is None:
        return None

    # Prefer direct linkage from notification -> email when available.
    # New email alerts set source_email_id even when no follow-up marker exists,
    # so reply commands should still work from that context.
    source_email_id = (notification.source_email_id or "").strip()
    if source_email_id:
        email_result = await db.execute(select(EmailItem).where(EmailItem.id == source_email_id))
        source_email = email_result.scalar_one_or_none()
        if source_email is not None:
            return _ResolvedEmailContext(
                resolved_notification_id=notification.id,
                follow_up_id=_extract_follow_up_id(notification.message),
                email_item=source_email,
            )

    follow_up_id = _extract_follow_up_id(notification.message)
    if not follow_up_id:
        return _ResolvedEmailContext(
            resolved_notification_id=notification.id,
            follow_up_id=None,
            email_item=None,
        )

    follow_up_result = await db.execute(select(FollowUpItem).where(FollowUpItem.id == follow_up_id))
    follow_up = follow_up_result.scalar_one_or_none()
    if follow_up is None:
        return _ResolvedEmailContext(
            resolved_notification_id=notification.id,
            follow_up_id=follow_up_id,
            email_item=None,
        )

    email_result = await db.execute(select(EmailItem).where(EmailItem.id == follow_up.email_id))
    email_item = email_result.scalar_one_or_none()

    return _ResolvedEmailContext(
        resolved_notification_id=notification.id,
        follow_up_id=follow_up_id,
        email_item=email_item,
    )


def _resolve_recipient(parsed_recipient: str | None, context_email: EmailItem | None) -> str | None:
    if parsed_recipient:
        return parsed_recipient
    if context_email and context_email.from_address:
        return context_email.from_address
    return None


def _extract_recipient_name_from_draft_body(body: str) -> str | None:
    first_line = (body or "").splitlines()[0].strip() if body else ""
    match = _DRAFT_GREETING_RE.match(first_line)
    if not match:
        return None
    candidate = re.sub(r"\s+", " ", match.group(1)).strip(" ,.;:-")
    return candidate or None


def _looks_like_contextual_affirmative_reply(
    transcript_text: str,
    *,
    context_email: EmailItem | None,
) -> bool:
    if context_email is None:
        return False

    text = (transcript_text or "").strip()
    if not text:
        return False
    if len(text) > 140:
        return False
    if _AFFIRMATIVE_REPLY_RE.search(text) is None:
        return False

    subject = (context_email.subject or "").strip()
    preview = (context_email.body_preview or "").strip()
    combined_context = f"{subject} {preview}".strip()
    if not combined_context:
        return False

    return _REQUEST_CONTEXT_RE.search(combined_context) is not None


def _is_meeting_request_context(context_email: EmailItem | None) -> bool:
    if context_email is None:
        return False
    combined = f"{(context_email.subject or '').strip()} {(context_email.body_preview or '').strip()}".strip()
    if not combined:
        return False
    return _MEETING_CONTEXT_RE.search(combined) is not None


def _normalize_meeting_reply_text(transcript_text: str) -> str:
    text = " ".join((transcript_text or "").strip().split())
    if not text:
        return ""

    normalized = text
    normalized = re.sub(
        r"\b(let'?s\s+make\s+it|make\s+it|move\s+it\s+to)\s+den\s+(?:ar|är)\b",
        r"\1 ten",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        r"\b(let'?s\s+make)\s+i\s+think\s+it'?s\b",
        r"\1 it",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        r"\b(make)\s+i\s+think\s+it'?s\b",
        r"\1 it",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        r"\b(let'?s)\s+(?:let'?s\s+)+",
        r"\1 ",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _classify_meeting_reply_mode(transcript_text: str, *, context_email: EmailItem | None) -> MeetingReplyMode:
    if not _is_meeting_request_context(context_email):
        return "none"

    text = _normalize_meeting_reply_text(transcript_text)
    if not text:
        return "none"

    control_kind, _ = classify_control_intent(text)
    if _NEGATIVE_REPLY_RE.search(text):
        if _COUNTER_REPLY_HINT_RE.search(text) or _SPOKEN_COUNTER_TIME_RE.search(text):
            return "counter"
        return "decline"

    if control_kind in {"send_control", "affirmative_short"}:
        return "accept"

    if (_COUNTER_REPLY_HINT_RE.search(text) or _SPOKEN_COUNTER_TIME_RE.search(text)) and re.search(r"\b(fine|works|available|can\s+do|can\s+make|let'?s)\b", text, re.IGNORECASE):
        return "counter"

    return "none"


def _build_calendar_utterance_from_email_context(
    transcript_text: str,
    *,
    context_email: EmailItem | None,
) -> str:
    normalized_reply = _normalize_meeting_reply_text(transcript_text)
    if normalized_reply and _BARE_TEN_REPLY_RE.search(normalized_reply):
        normalized_reply = _BARE_TEN_REPLY_RE.sub(r"\g<0> am", normalized_reply)

    requested_time_hint = _format_requested_time_hint(normalized_reply or transcript_text)
    has_explicit_change = _has_explicit_schedule_change(normalized_reply or transcript_text)

    attendee = ""
    if context_email is not None:
        from_name = (context_email.from_name or "").strip()
        from_address = (context_email.from_address or "").strip()
        if from_name and from_address:
            attendee = f"{from_name} <{from_address}>"
        else:
            attendee = from_name or from_address

    parts: list[str] = []
    if attendee:
        parts.append(f"Schedule a meeting with {attendee}.")

    if requested_time_hint:
        parts.append(f"Requested new time: {requested_time_hint}.")
    parts.append(f"My reply to the meeting request: {normalized_reply or transcript_text.strip()}")

    if has_explicit_change:
        parts.append("The reply explicitly changes the meeting time.")

    if context_email is not None:
        subject = (context_email.subject or "").strip()
        preview = (context_email.body_preview or "").strip()
        if subject:
            parts.append(f"Subject: {subject}")
        if preview:
            parts.append(f"Email context: {preview}")

    if not has_explicit_change and not _DAY_REFERENCE_RE.search(normalized_reply or transcript_text) and context_email is not None:
        parts.append("Keep the same day or date from the original meeting request unless my reply explicitly changes it.")

    return " ".join(parts)


def _should_delegate_invite_to_sender(transcript_text: str) -> bool:
    text = (transcript_text or "").strip()
    if not text:
        return False
    return _DELEGATE_INVITE_RE.search(text) is not None


def _has_explicit_schedule_change(transcript_text: str) -> bool:
    text = _normalize_meeting_reply_text(transcript_text)
    if not text:
        return False
    if _DAY_REFERENCE_RE.search(text):
        return True
    return _EXPLICIT_COUNTER_TIME_RE.search(text) is not None


async def handle_email_command_from_transcript(
    db: AsyncSession,
    *,
    notification_id: str | None,
    transcript_text: str,
    correlation_id: str | None = None,
) -> ServiceExecutionOutcome:
    resolved = await _resolve_context(db, notification_id=notification_id)
    llm_config = await get_llm_config(db)
    effective_notification_id = notification_id or (resolved.resolved_notification_id if resolved else None)

    context_email = resolved.email_item if resolved else None
    compact_context = preprocess_email_context(
        message_id=(context_email.id if context_email else None),
        conversation_id=(context_email.conversation_id if context_email else None),
        from_address=(context_email.from_address if context_email else None),
        subject=(context_email.subject if context_email else None),
        body_preview=(context_email.body_preview if context_email else None),
        user_utterance=transcript_text,
    )

    try:
        parsed = await parse_email_user_action(
            db,
            utterance=transcript_text,
            context=compact_context,
        )
    except Exception as exc:
        logger.warning("email_action_parser failed: %s", exc)
        return ServiceExecutionOutcome()

    if parsed.usage is not None:
        await record_llm_usage(
            db,
            interaction_kind="email_command_parse",
            provider=llm_config.provider,
            model=llm_config.model or "gpt-5.4-mini",
            usage=parsed.usage,
            source_email_id=(context_email.id if context_email else None),
            notification_id=effective_notification_id,
            metadata_json={"correlation_id": correlation_id, "action": parsed.action},
        )

    if parsed.action == "none":
        meeting_reply_mode = _classify_meeting_reply_mode(transcript_text, context_email=context_email)
        if meeting_reply_mode in {"accept", "counter", "decline"}:
            if meeting_reply_mode == "decline":
                instruction = "Politely decline this meeting invitation and say I cannot make that time."
            else:
                instruction = transcript_text.strip()
            parsed = ParsedEmailAction(
                action="reply",
                recipient=None,
                subject_hint=None,
                message_instructions=instruction,
                reasoning=f"heuristic:meeting_reply_{meeting_reply_mode}",
            )
        elif _looks_like_contextual_affirmative_reply(transcript_text, context_email=context_email):
            parsed = ParsedEmailAction(
                action="reply",
                recipient=None,
                subject_hint=None,
                message_instructions=transcript_text.strip(),
                reasoning="heuristic:contextual_affirmative_reply",
            )
        else:
            return ServiceExecutionOutcome()

    async def create_pending_draft(
        *,
        mode: str,
        recipient_email: str | None,
        subject: str,
        body: str,
        suggestions: list[dict] | None = None,
    ) -> ServiceExecutionOutcome:
        draft = await draft_runtime.create_draft(
            db,
            mode=mode,
            recipient_email=recipient_email,
            subject=subject,
            body=body,
            source_email_id=(context_email.id if context_email else None),
            source_notification_id=effective_notification_id,
            suggestions=suggestions,
            metadata={"correlation_id": correlation_id, "parsed_action": parsed.action},
        )
        draft_notification = await create_notification(
            db,
            message=build_email_draft_notification_message(
                draft_id=draft.id,
                recipient_email=draft.recipient_email,
            ),
            notification_type="info",
            source_email_id=(context_email.id if context_email else None),
            details=build_email_draft_notification_details(
                recipient_email=draft.recipient_email,
                source_notification_id=effective_notification_id,
            ),
        )
        await draft_runtime.attach_send_notification(
            db,
            draft_id=draft.id,
            notification_id=draft_notification.id,
        )
        await push_notification(draft_notification)

        return ServiceExecutionOutcome(
            result="email_draft_ready",
            display_text="Draft prepared. Review recipient/subject/body and confirm with 'send it'.",
            interaction=ClientInteractionOutcome(
                dismiss_notification_id=effective_notification_id,
                close_window=False,
            ),
        )

    if parsed.action == "reply":
        if context_email is None:
            return ServiceExecutionOutcome(
                result="email_reply_unavailable",
                display_text="I can reply when this notification is linked to a specific email.",
            )

        drafted = await draft_email(
            db,
            context=compact_context,
            user_instruction=parsed.message_instructions or transcript_text,
            mode="reply",
            default_subject=f"Re: {context_email.subject}" if context_email.subject else "Re:",
        )

        if drafted.usage is not None:
            await record_llm_usage(
                db,
                interaction_kind="email_reply_draft",
                provider=llm_config.provider,
                model=llm_config.model or "gpt-5.4-mini",
                usage=drafted.usage,
                source_email_id=context_email.id,
                notification_id=effective_notification_id,
                metadata_json={"correlation_id": correlation_id, "mode": "reply"},
            )
        draft_outcome = await create_pending_draft(
            mode="reply",
            recipient_email=context_email.from_address,
            subject=drafted.subject,
            body=drafted.body,
            suggestions=None,
        )

        meeting_reply_mode = _classify_meeting_reply_mode(transcript_text, context_email=context_email)
        should_prepare_calendar = (
            meeting_reply_mode == "accept"
            or (meeting_reply_mode == "counter" and _has_explicit_schedule_change(transcript_text))
        )
        if should_prepare_calendar and not _should_delegate_invite_to_sender(transcript_text):
            try:
                from ..calendar.commands import handle_calendar_command_from_transcript

                calendar_outcome = await handle_calendar_command_from_transcript(
                    db,
                    notification_id=effective_notification_id,
                    transcript_text=_build_calendar_utterance_from_email_context(
                        transcript_text,
                        context_email=context_email,
                    ),
                    correlation_id=correlation_id,
                )
            except Exception as exc:
                logger.warning("meeting_reply_calendar_proposal failed: %s", exc)
                calendar_outcome = ServiceExecutionOutcome()

            if calendar_outcome.result == "calendar_proposal_ready":
                return ServiceExecutionOutcome(
                    result="email_and_calendar_ready",
                    display_text=(
                        "Draft prepared for your reply. "
                        "A meeting proposal is also ready. "
                        "Say 'send it' to send the email draft, then approve or edit the calendar proposal."
                    ),
                    interaction=draft_outcome.interaction,
                )

        return draft_outcome

    if parsed.action == "new_email":
        recipient = _resolve_recipient(parsed.recipient, context_email)
        if recipient is None:
            recipient = extract_recipient_from_text(transcript_text)
        suggestions: list[dict] = []
        recipient_query = transcript_text
        if recipient is not None and extract_recipient_from_text(recipient) is None:
            recipient_query = recipient
            recipient = None

        if recipient is None:
            candidates = await resolve_contact_candidates(db, raw_query=recipient_query)
            suggestions = [
                {
                    "email": candidate.email,
                    "label": candidate.label,
                    "confidence": candidate.confidence,
                    "source": candidate.source,
                }
                for candidate in candidates
            ]
            if len(candidates) == 1 and candidates[0].confidence >= 0.7:
                recipient = candidates[0].email

        default_subject = parsed.subject_hint or (context_email.subject if context_email else "Quick update")
        drafted = await draft_email(
            db,
            context=compact_context,
            user_instruction=parsed.message_instructions or transcript_text,
            mode="new_email",
            default_subject=default_subject,
        )

        if recipient is None and not suggestions:
            salutation_recipient = _extract_recipient_name_from_draft_body(drafted.body)
            if salutation_recipient is not None:
                candidates = await resolve_contact_candidates(db, raw_query=salutation_recipient)
                suggestions = [
                    {
                        "email": candidate.email,
                        "label": candidate.label,
                        "confidence": candidate.confidence,
                        "source": candidate.source,
                    }
                    for candidate in candidates
                ]
                if len(candidates) == 1 and candidates[0].confidence >= 0.7:
                    recipient = candidates[0].email

        if drafted.usage is not None:
            await record_llm_usage(
                db,
                interaction_kind="email_new_draft",
                provider=llm_config.provider,
                model=llm_config.model or "gpt-5.4-mini",
                usage=drafted.usage,
                source_email_id=(context_email.id if context_email else None),
                notification_id=effective_notification_id,
                metadata_json={"correlation_id": correlation_id, "mode": "new_email"},
            )
        return await create_pending_draft(
            mode="new_email",
            recipient_email=recipient,
            subject=drafted.subject,
            body=drafted.body,
            suggestions=suggestions,
        )

    return ServiceExecutionOutcome()
