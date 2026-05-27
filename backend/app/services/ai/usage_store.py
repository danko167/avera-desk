from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.tables import LlmUsageRecord
from .usage import LlmUsage


async def record_llm_usage(
    db: AsyncSession,
    *,
    interaction_kind: str,
    provider: str,
    model: str,
    usage: LlmUsage,
    source_email_id: str | None = None,
    notification_id: str | None = None,
    conversation_turn_id: str | None = None,
    metadata_json: dict | None = None,
) -> None:
    db.add(
        LlmUsageRecord(
            id=str(uuid.uuid4()),
            interaction_kind=interaction_kind,
            provider=provider,
            model=model,
            source_email_id=source_email_id,
            notification_id=notification_id,
            conversation_turn_id=conversation_turn_id,
            prompt_tokens=int(usage.prompt_tokens),
            completion_tokens=int(usage.completion_tokens),
            total_tokens=int(usage.total_tokens),
            metadata_json=metadata_json or {},
            created_at=datetime.now(timezone.utc),
        )
    )
    await db.commit()


async def get_llm_usage_summary(db: AsyncSession) -> dict[str, int]:
    result = await db.execute(
        select(
            func.coalesce(func.sum(LlmUsageRecord.prompt_tokens), 0),
            func.coalesce(func.sum(LlmUsageRecord.completion_tokens), 0),
            func.coalesce(func.sum(LlmUsageRecord.total_tokens), 0),
            func.count(LlmUsageRecord.id),
        )
    )
    prompt_tokens, completion_tokens, total_tokens, record_count = result.one()
    return {
        "prompt_tokens": int(prompt_tokens or 0),
        "completion_tokens": int(completion_tokens or 0),
        "total_tokens": int(total_tokens or 0),
        "record_count": int(record_count or 0),
    }
