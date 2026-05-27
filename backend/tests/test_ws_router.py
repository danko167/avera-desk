import unittest
from unittest.mock import AsyncMock, patch

from app.services.ws import router as ws_router


class WsRouterDispatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_route_dispatches_dismiss_notification(self) -> None:
        websocket = object()
        db = object()
        session_audio_bytes = 123
        message = {"type": "dismiss_notification", "id": "notif-1"}

        with patch(
            "app.services.ws.router.handlers.handle_dismiss_notification",
            new=AsyncMock(),
        ) as dismiss_handler:
            result = await ws_router.route_ws_message(
                websocket,
                message,
                db,
                session_audio_bytes,
            )

        dismiss_handler.assert_awaited_once_with(message, db)
        self.assertEqual(result, session_audio_bytes)

    async def test_route_dispatches_text_command(self) -> None:
        websocket = object()
        db = object()
        session_audio_bytes = 0
        message = {"type": "text_command", "text": "reply", "notification_id": "notif-1"}

        with patch(
            "app.services.ws.router.handlers.handle_text_command",
            new=AsyncMock(),
        ) as text_handler:
            result = await ws_router.route_ws_message(
                websocket,
                message,
                db,
                session_audio_bytes,
            )

        text_handler.assert_awaited_once_with(websocket, message, db)
        self.assertEqual(result, session_audio_bytes)

    async def test_route_resets_audio_bytes_on_audio_start(self) -> None:
        websocket = object()
        db = object()
        session_audio_bytes = 4096
        message = {"type": "audio_start", "notification_id": "notif-1"}

        with patch(
            "app.services.ws.router.handlers.handle_audio_start",
            new=AsyncMock(),
        ) as audio_start_handler:
            result = await ws_router.route_ws_message(
                websocket,
                message,
                db,
                session_audio_bytes,
            )

        audio_start_handler.assert_awaited_once_with(websocket, message, db)
        self.assertEqual(result, 0)

    async def test_route_resets_audio_bytes_on_audio_stop(self) -> None:
        websocket = object()
        db = object()
        session_audio_bytes = 4096
        message = {"type": "audio_stop"}

        with patch(
            "app.services.ws.router.handlers.handle_audio_stop",
            new=AsyncMock(),
        ) as audio_stop_handler:
            result = await ws_router.route_ws_message(
                websocket,
                message,
                db,
                session_audio_bytes,
            )

        audio_stop_handler.assert_awaited_once_with(websocket)
        self.assertEqual(result, 0)

    async def test_db_required_message_without_db_returns_protocol_error(self) -> None:
        websocket = AsyncMock()
        session_audio_bytes = 7
        message = {"type": "text_command", "text": "reply"}

        with patch(
            "app.services.ws.router.handlers.handle_text_command",
            new=AsyncMock(),
        ) as text_handler:
            result = await ws_router.route_ws_message(
                websocket,
                message,
                None,
                session_audio_bytes,
            )

        text_handler.assert_not_awaited()
        websocket.send_json.assert_awaited_once_with(
            {
                "type": "protocol_error",
                "detail": "Database context required for message type: text_command",
                "message_type": "text_command",
            }
        )
        self.assertEqual(result, session_audio_bytes)


if __name__ == "__main__":
    unittest.main()
