from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from ...schemas import Notification
from ..shared import notifications as notification_service


async def _send_json_if_connected(websocket: WebSocket, payload: dict) -> bool:
    try:
        await websocket.send_json(payload)
        return True
    except WebSocketDisconnect:
        return False
    except RuntimeError as exc:
        message = str(exc)
        if (
            "WebSocket is not connected" in message
            or "close message has been sent" in message
        ):
            return False
        raise


@dataclass(slots=True)
class ClientInteractionOutcome:
    dismissed_notification: Notification | None = None
    dismiss_notification_id: str | None = None
    close_window: bool = False
    close_delay_ms: int = 4000
    close_only_if_last_unread: bool = True


@asynccontextmanager
async def feedback_processing(websocket: WebSocket, *, active: bool):
    if active:
        await _send_json_if_connected(websocket, {"type": "feedback_processing", "active": True})
    try:
        yield
    finally:
        if active:
            await _send_json_if_connected(websocket, {"type": "feedback_processing", "active": False})


async def apply_client_interaction_outcome(
    websocket: WebSocket,
    db: AsyncSession,
    *,
    outcome: ClientInteractionOutcome,
) -> None:
    dismissed_notification = outcome.dismissed_notification
    if dismissed_notification is None and outcome.dismiss_notification_id:
        dismissed_notification = await notification_service.dismiss_notification(
            db,
            outcome.dismiss_notification_id,
        )

    if dismissed_notification is not None:
        await notification_service.push_notification(dismissed_notification)

    if outcome.close_window:
        await _send_json_if_connected(
            websocket,
            {
                "type": "close_window_after",
                "delay_ms": outcome.close_delay_ms,
                "only_if_last_unread": outcome.close_only_if_last_unread,
            }
        )