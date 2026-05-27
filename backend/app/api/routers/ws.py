from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from ...core.local_security import (
    consume_local_ws_ticket,
    is_allowed_origin,
    parse_allowed_origins,
    should_enforce_local_auth,
)
from ...core import websocket_state as state
from ...db import db_session
from ...services import shared, ws

router = APIRouter()
logger = logging.getLogger(__name__)
_ALLOWED_ORIGINS = parse_allowed_origins()
_DB_REQUIRED_MESSAGE_TYPES = {
    "mock_trigger",
    "dismiss_notification",
    "text_command",
    "audio_start",
}


@router.websocket("/ws")
async def websocket_events(websocket: WebSocket) -> None:
    if should_enforce_local_auth():
        origin = websocket.headers.get("origin")
        if not is_allowed_origin(origin, allowed_origins=_ALLOWED_ORIGINS):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="WebSocket origin is not allowed.")
            return

        ws_ticket = websocket.query_params.get("ws_ticket")
        if not consume_local_ws_ticket(ws_ticket):
            await websocket.close(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Missing or invalid WebSocket auth ticket.",
            )
            return

    await websocket.accept()
    logger.info("ws_client_connected")
    await state.add_connection(websocket)

    try:
        async with db_session() as db:
            recent = await shared.get_recent_notifications(db)
        try:
            await websocket.send_json(await state.get_snapshot(recent))
        except WebSocketDisconnect:
            logger.info("ws_client_disconnected_before_snapshot")
            return

        session_audio_bytes = 0
        while True:
            try:
                message = await websocket.receive_json()
            except WebSocketDisconnect:
                logger.info("ws_client_disconnected")
                break
            except RuntimeError as exc:
                # Starlette may raise RuntimeError when the socket is already closed.
                # Treat this as a normal disconnect to avoid noisy ASGI traces.
                if "WebSocket is not connected" in str(exc):
                    logger.info("ws_client_disconnected")
                    break
                raise
            except ValueError as exc:
                logger.warning("ws_invalid_json_payload error=%s", exc)
                await websocket.send_json(
                    {
                        "type": "protocol_error",
                        "detail": "Invalid websocket JSON payload.",
                        "message_type": None,
                    }
                )
                continue

            if not isinstance(message, dict):
                await websocket.send_json(
                    {
                        "type": "protocol_error",
                        "detail": "Malformed websocket frame: expected object with non-empty string 'type'.",
                        "message_type": None,
                    }
                )
                continue

            message_type = message.get("type")
            if not isinstance(message_type, str) or not message_type.strip():
                await websocket.send_json(
                    {
                        "type": "protocol_error",
                        "detail": "Malformed websocket frame: expected object with non-empty string 'type'.",
                        "message_type": message_type if isinstance(message_type, str) else None,
                    }
                )
                continue

            logger.debug("ws_message_received type=%s", message_type)

            if message_type in _DB_REQUIRED_MESSAGE_TYPES:
                async with db_session() as db:
                    session_audio_bytes = await ws.route_ws_message(
                        websocket,
                        message,
                        db,
                        session_audio_bytes,
                    )
            else:
                session_audio_bytes = await ws.route_ws_message(
                    websocket,
                    message,
                    None,
                    session_audio_bytes,
                )

    except WebSocketDisconnect:
        logger.info("ws_client_disconnected")
    finally:
        await ws.handle_ws_disconnect(websocket)
        await state.remove_connection(websocket)
        logger.debug("ws_cleanup_complete")
