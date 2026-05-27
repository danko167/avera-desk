from __future__ import annotations

import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.control_intent import classify_control_intent
from ..interaction.client_feedback import ClientInteractionOutcome
from ..shared.outcome import ServiceExecutionOutcome
from .parser import extract_recipient_from_text
from . import draft_runtime

_CHANGE_RECIPIENT_RE = re.compile(r"\b(?:recipient|to)\b", re.IGNORECASE)


async def handle_email_draft_command_from_transcript(
    db: AsyncSession,
    *,
    draft_id: str,
    transcript_text: str,
    notification_id: str | None,
) -> ServiceExecutionOutcome:
    utterance = (transcript_text or "").strip()
    if not utterance:
        return ServiceExecutionOutcome()

    control_kind, _ = classify_control_intent(utterance)

    if control_kind == "cancel_control":
        draft = await draft_runtime.cancel_draft(db, draft_id=draft_id)
        if draft is None:
            return ServiceExecutionOutcome()
        dismiss_notification_id = notification_id or draft.send_notification_id or draft.source_notification_id
        return ServiceExecutionOutcome(
            result="email_draft_canceled",
            display_text="Draft canceled.",
            interaction=ClientInteractionOutcome(
                dismiss_notification_id=dismiss_notification_id,
                close_window=True,
            ),
        )

    if _CHANGE_RECIPIENT_RE.search(utterance):
        recipient = extract_recipient_from_text(utterance)
        if recipient:
            draft = await draft_runtime.update_draft(
                db,
                draft_id=draft_id,
                recipient_email=recipient,
            )
            if draft is not None:
                return ServiceExecutionOutcome(
                    result="email_draft_recipient_updated",
                    display_text=f"Recipient updated to {recipient}.",
                )

    if control_kind in {"send_control", "affirmative_short"}:
        draft = await draft_runtime.send_draft(db, draft_id=draft_id)
        if draft is None:
            return ServiceExecutionOutcome(
                result="email_draft_send_failed",
                display_text="Unable to send draft. Verify recipient and try again.",
            )
        recipient = draft.recipient_email or "recipient"
        return ServiceExecutionOutcome(
            result="email_draft_sent",
            display_text=f"Email sent to {recipient}.",
            interaction=ClientInteractionOutcome(
                dismiss_notification_id=notification_id,
                close_window=True,
            ),
        )

    return ServiceExecutionOutcome()
