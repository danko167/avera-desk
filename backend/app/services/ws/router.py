from fastapi import WebSocket
from sqlalchemy.ext.asyncio import AsyncSession

from . import handlers


async def route_ws_message(
    websocket: WebSocket,
    message: dict,
    db: AsyncSession | None,
    session_audio_bytes: int,
) -> int:
    message_type = message.get("type")

    if message_type == "ping":
        await handlers.handle_ping(websocket)
    elif message_type == "set_status":
        await handlers.handle_set_status(message)
    elif message_type == "mock_trigger":
        if db is None:
            await websocket.send_json(
                {
                    "type": "protocol_error",
                    "detail": "Database context required for message type: mock_trigger",
                    "message_type": message_type,
                }
            )
            return session_audio_bytes
        await handlers.handle_mock_trigger(message, db)
    elif message_type == "dismiss_notification":
        if db is None:
            await websocket.send_json(
                {
                    "type": "protocol_error",
                    "detail": "Database context required for message type: dismiss_notification",
                    "message_type": message_type,
                }
            )
            return session_audio_bytes
        await handlers.handle_dismiss_notification(message, db)
    elif message_type == "text_command":
        if db is None:
            await websocket.send_json(
                {
                    "type": "protocol_error",
                    "detail": "Database context required for message type: text_command",
                    "message_type": message_type,
                }
            )
            return session_audio_bytes
        await handlers.handle_text_command(websocket, message, db)
    elif message_type == "audio_start":
        if db is None:
            await websocket.send_json(
                {
                    "type": "protocol_error",
                    "detail": "Database context required for message type: audio_start",
                    "message_type": message_type,
                }
            )
            return session_audio_bytes
        await handlers.handle_audio_start(websocket, message, db)
        session_audio_bytes = 0
    elif message_type == "audio_blob":
        session_audio_bytes = await handlers.handle_audio_blob(
            websocket,
            message,
            session_audio_bytes,
        )
    elif message_type == "audio_stop":
        await handlers.handle_audio_stop(websocket)
        session_audio_bytes = 0
    else:
        await websocket.send_json(
            {
                "type": "protocol_error",
                "detail": f"Unknown websocket message type: {message_type!r}",
                "message_type": message_type,
            }
        )

    return session_audio_bytes
