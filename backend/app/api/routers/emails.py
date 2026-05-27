from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math

from fastapi import APIRouter, Query

from ...db import db_session
from ...integrations.email_provider import get_oauth_module, normalize_email_provider
from ...services import email, followups as follow_ups, shared, workers

router = APIRouter()


@router.get("/emails/recent")
async def get_recent_emails(limit: int = Query(default=50, ge=1, le=500)) -> dict:
    async with db_session() as db:
        emails = await shared.get_recent_email_summaries(db, limit=limit)
        return {"emails": emails, "count": len(emails)}


@router.post("/emails/sync")
async def sync_emails_now() -> dict[str, object]:
    async with db_session() as db:
        settings = await shared.get_settings(db)
        email_provider = normalize_email_provider(settings.get("email_provider"))
        oauth = get_oauth_module(email_provider)

    if not oauth.is_authenticated():
        return {"status": "not authenticated", "count": 0, "new_emails": []}

    async with db_session() as db:
        count, new_emails = await email.sync_inbox(db)
        created_followups = await follow_ups.upsert_followups_for_email_ids(
            db,
            email_ids=[email_item["id"] for email_item in new_emails],
        )
        await workers.push_new_email_notifications(
            db,
            new_emails=new_emails,
            created_followups=created_followups,
        )

        return {
            "status": "synced",
            "count": count,
            "new_emails": new_emails,
            "followups_created": len(created_followups),
        }


@router.get("/emails/sync-status")
async def get_email_sync_status() -> dict[str, object | None]:
    now = datetime.now(timezone.utc)

    async with db_session() as db:
        settings = await shared.get_settings(db)

    email_provider = normalize_email_provider(settings.get("email_provider"))
    oauth = get_oauth_module(email_provider)

    sync_interval_minutes = int(settings.get("email_sync_interval_minutes", 5))
    sync_interval_minutes = max(1, min(60, sync_interval_minutes))
    sync_interval_seconds = sync_interval_minutes * 60

    runtime_state = workers.get_email_sync_runtime_state()

    effective_next_sync_at: datetime | None = None
    if runtime_state.last_sync_finished_at is not None:
        effective_next_sync_at = runtime_state.last_sync_finished_at + timedelta(seconds=sync_interval_seconds)
    elif runtime_state.next_sync_at is not None:
        effective_next_sync_at = runtime_state.next_sync_at

    seconds_until_next_sync: int | None = None
    if effective_next_sync_at is not None:
        seconds_until_next_sync = max(0, math.ceil((effective_next_sync_at - now).total_seconds()))

    return {
        "authenticated": oauth.is_authenticated(),
        "sync_interval_minutes": sync_interval_minutes,
        "next_sync_at": effective_next_sync_at.isoformat() if effective_next_sync_at else None,
        "last_sync_started_at": runtime_state.last_sync_started_at.isoformat() if runtime_state.last_sync_started_at else None,
        "last_sync_finished_at": runtime_state.last_sync_finished_at.isoformat() if runtime_state.last_sync_finished_at else None,
        "seconds_until_next_sync": seconds_until_next_sync,
    }
