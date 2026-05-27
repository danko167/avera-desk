from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ...db import db_session
from ...schemas import FollowUpItemDto
from ...services import followups as follow_ups

router = APIRouter()


@router.get("/followups", response_model=list[FollowUpItemDto])
async def get_followups(
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[FollowUpItemDto]:
    async with db_session() as db:
        return await follow_ups.list_followups(db, status=status, limit=limit)


@router.get("/followups/{follow_up_id}", response_model=FollowUpItemDto)
async def get_followup_by_id(follow_up_id: str) -> FollowUpItemDto:
    async with db_session() as db:
        item = await follow_ups.get_followup_by_id(db, follow_up_id=follow_up_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Follow-up not found")
    return item
