from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ...db import db_session
from ...schemas import EmailDraftDto, UpdateEmailDraftRequest
from ...services.email import draft_runtime as email_drafts

router = APIRouter()


@router.get("/email-drafts/{draft_id}", response_model=EmailDraftDto)
async def get_email_draft_by_id(draft_id: str) -> EmailDraftDto:
    async with db_session() as db:
        draft = await email_drafts.get_draft_by_id(db, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Email draft not found")
    return draft


@router.patch("/email-drafts/{draft_id}", response_model=EmailDraftDto)
async def patch_email_draft(draft_id: str, payload: UpdateEmailDraftRequest) -> EmailDraftDto:
    async with db_session() as db:
        draft = await email_drafts.update_draft(
            db,
            draft_id=draft_id,
            recipient_email=payload.recipient_email,
            subject=payload.subject,
            body=payload.body,
        )
    if draft is None:
        raise HTTPException(status_code=404, detail="Pending email draft not found")
    return draft


@router.post("/email-drafts/{draft_id}/send", response_model=EmailDraftDto)
async def send_email_draft(draft_id: str) -> EmailDraftDto:
    async with db_session() as db:
        draft = await email_drafts.send_draft(db, draft_id=draft_id)
    if draft is None:
        raise HTTPException(status_code=400, detail="Unable to send draft")
    return draft


@router.post("/email-drafts/{draft_id}/cancel", response_model=EmailDraftDto)
async def cancel_email_draft(draft_id: str) -> EmailDraftDto:
    async with db_session() as db:
        draft = await email_drafts.cancel_draft(db, draft_id=draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Email draft not found")
    return draft
