from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ....db.tables import NotificationRecord
from ...common.followup_markers import extract_follow_up_id


_CAL_PROPOSAL_RE = re.compile(r"\[cal:(?P<proposal_id>[A-Za-z0-9\-]+)\]")


def extract_draft_id(message: str) -> str | None:
    marker = "[draft:"
    start = (message or "").find(marker)
    if start < 0:
        return None
    start += len(marker)
    end = (message or "").find("]", start)
    if end < 0:
        return None
    value = (message or "")[start:end].strip()
    return value or None


def extract_calendar_proposal_id(message: str) -> str | None:
    match = _CAL_PROPOSAL_RE.search(message or "")
    if not match:
        return None
    value = (match.group("proposal_id") or "").strip()
    return value or None


async def load_world_state(db: AsyncSession, *, notification_id: str | None):
    from .models import WorldState

    state = WorldState(
        notification_id=notification_id,
        has_notification_context=bool(notification_id),
    )

    if not notification_id:
        return state

    result = await db.execute(select(NotificationRecord).where(NotificationRecord.id == notification_id))
    notification = result.scalar_one_or_none()
    if notification is None:
        return state

    state.draft_id = extract_draft_id(notification.message)
    state.calendar_proposal_id = extract_calendar_proposal_id(notification.message)
    state.follow_up_id = extract_follow_up_id(notification.message)
    return state
