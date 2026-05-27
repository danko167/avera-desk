from __future__ import annotations

import uuid
import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.tables import ConversationTurnRecord
from ...schemas import ConversationTurn


def _normalize_for_compare(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _is_progressive_refinement(previous: str, current: str) -> bool:
    prev = _normalize_for_compare(previous)
    curr = _normalize_for_compare(current)
    if not prev or not curr:
        return False
    if prev == curr:
        return True
    return curr.startswith(prev) or prev.startswith(curr)


def _prefer_more_complete(previous: str, current: str) -> str:
    return current if len(current.strip()) >= len(previous.strip()) else previous


def _record_to_pydantic(record: ConversationTurnRecord) -> ConversationTurn:
    return ConversationTurn(
        id=record.id,
        text=record.text,
        role=record.role,
        mode=record.mode,
        session_id=record.session_id,
        source=record.source,
        notification_id=record.notification_id,
        timestamp=record.timestamp.isoformat(),
    )


async def create_conversation_turn(
    db: AsyncSession,
    *,
    text: str,
    role: str = "user",
    mode: str,
    session_id: str | None,
    source: str,
    notification_id: str | None,
) -> ConversationTurn | None:
    normalized = text.strip()
    if not normalized:
        return None

    now = datetime.now(timezone.utc)

    if session_id:
        session_result = await db.execute(
            select(ConversationTurnRecord)
            .where(ConversationTurnRecord.session_id == session_id)
            .order_by(ConversationTurnRecord.timestamp.desc())
            .limit(1)
        )
        session_latest = session_result.scalar_one_or_none()
        if (
            session_latest is not None
            and session_latest.role == role
            and session_latest.mode == mode
            and session_latest.source == source
            and session_latest.notification_id == notification_id
            and _is_progressive_refinement(session_latest.text, normalized)
        ):
            session_latest.text = _prefer_more_complete(session_latest.text, normalized)
            session_latest.timestamp = now
            await db.commit()
            await db.refresh(session_latest)
            return _record_to_pydantic(session_latest)

    # Basic dedupe for repeated finals emitted back-to-back by upstream.
    latest_result = await db.execute(
        select(ConversationTurnRecord)
        .order_by(ConversationTurnRecord.timestamp.desc())
        .limit(1)
    )
    latest = latest_result.scalar_one_or_none()
    if latest is not None:
        latest_timestamp = latest.timestamp
        if latest_timestamp.tzinfo is None:
            latest_timestamp = latest_timestamp.replace(tzinfo=timezone.utc)
        age_seconds = (now - latest_timestamp).total_seconds()
        if (
            age_seconds <= 2.0
            and latest.text == normalized
            and latest.mode == mode
            and latest.notification_id == notification_id
        ):
            return _record_to_pydantic(latest)

    record = ConversationTurnRecord(
        id=str(uuid.uuid4()),
        text=normalized,
        role=role,
        mode=mode,
        session_id=session_id,
        source=source,
        notification_id=notification_id,
        timestamp=now,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return _record_to_pydantic(record)


async def get_recent_conversation_turns(
    db: AsyncSession,
    *,
    limit: int = 200,
) -> list[ConversationTurn]:
    result = await db.execute(
        select(ConversationTurnRecord)
        .order_by(ConversationTurnRecord.timestamp.desc())
        .limit(limit)
    )
    return [_record_to_pydantic(record) for record in result.scalars()]
