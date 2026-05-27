from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from ...core.local_security import (
    get_local_auth_token,
    is_allowed_origin,
    issue_local_ws_ticket,
    parse_allowed_origins,
    should_trust_forwarded_headers,
)
from ...core.url_validation import is_loopback_host

router = APIRouter()
logger = logging.getLogger(__name__)
_ALLOWED_ORIGINS = parse_allowed_origins()


def _is_loopback_request(request: Request) -> bool:
    direct_client_host = request.client.host if request.client is not None else None
    if is_loopback_host(direct_client_host):
        return True

    if not should_trust_forwarded_headers():
        return False

    forwarded_for = (request.headers.get("x-forwarded-for") or "").strip()
    if forwarded_for:
        first_hop = forwarded_for.split(",", 1)[0].strip()
        if is_loopback_host(first_hop):
            return True

    return False


def _require_local_bootstrap_request(request: Request) -> None:
    if not _is_loopback_request(request):
        logger.warning(
            "local_auth_bootstrap_rejected_non_loopback client=%s x_forwarded_for=%s",
            request.client.host if request.client is not None else None,
            request.headers.get("x-forwarded-for"),
        )
        raise HTTPException(status_code=403, detail="Local auth bootstrap is only allowed from loopback clients.")

    origin = (request.headers.get("origin") or "").strip()
    if origin and not is_allowed_origin(origin, allowed_origins=_ALLOWED_ORIGINS):
        logger.warning("local_auth_bootstrap_rejected_origin origin=%s", origin)
        raise HTTPException(status_code=403, detail="Request origin is not allowed.")


@router.get("/local-auth/token")
async def get_local_auth_session_token(request: Request) -> dict[str, str]:
    _require_local_bootstrap_request(request)
    logger.info(
        "local_auth_token_issued client=%s origin=%s",
        request.client.host if request.client is not None else None,
        request.headers.get("origin"),
    )
    return {"token": get_local_auth_token()}


@router.post("/local-auth/ws-ticket")
async def issue_local_auth_ws_ticket(request: Request) -> dict[str, object]:
    _require_local_bootstrap_request(request)
    logger.info(
        "local_auth_ws_ticket_issued client=%s origin=%s",
        request.client.host if request.client is not None else None,
        request.headers.get("origin"),
    )
    return {
        "ticket": issue_local_ws_ticket(),
        "expires_in_seconds": 45,
    }
