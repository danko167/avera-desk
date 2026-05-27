import unittest
from unittest.mock import AsyncMock, patch

from fastapi import WebSocketDisconnect

from app.api.routers import ws as ws_api_router


class _FakeDbSession:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, _exc_type, _exc, _tb):
        return False


class WsApiRouterValidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_non_object_frame_returns_protocol_error_without_dispatch(self) -> None:
        websocket = AsyncMock()
        websocket.headers = {}
        websocket.query_params = {}
        websocket.receive_json = AsyncMock(side_effect=[[], WebSocketDisconnect(1000)])

        with (
            patch("app.api.routers.ws.should_enforce_local_auth", return_value=False),
            patch("app.api.routers.ws.state.add_connection", new=AsyncMock()),
            patch("app.api.routers.ws.state.remove_connection", new=AsyncMock()),
            patch("app.api.routers.ws.state.get_snapshot", new=AsyncMock(return_value={"type": "snapshot"})),
            patch("app.api.routers.ws.shared.get_recent_notifications", new=AsyncMock(return_value=[])),
            patch("app.api.routers.ws.db_session", side_effect=lambda: _FakeDbSession()),
            patch("app.api.routers.ws.ws.handle_ws_disconnect", new=AsyncMock()),
            patch("app.api.routers.ws.ws.route_ws_message", new=AsyncMock()) as route_ws_message,
        ):
            await ws_api_router.websocket_events(websocket)

        route_ws_message.assert_not_awaited()
        protocol_error = {
            "type": "protocol_error",
            "detail": "Malformed websocket frame: expected object with non-empty string 'type'.",
            "message_type": None,
        }
        self.assertIn(((protocol_error,), {}), websocket.send_json.await_args_list)

    async def test_empty_type_returns_protocol_error_without_dispatch(self) -> None:
        websocket = AsyncMock()
        websocket.headers = {}
        websocket.query_params = {}
        websocket.receive_json = AsyncMock(side_effect=[{"type": ""}, WebSocketDisconnect(1000)])

        with (
            patch("app.api.routers.ws.should_enforce_local_auth", return_value=False),
            patch("app.api.routers.ws.state.add_connection", new=AsyncMock()),
            patch("app.api.routers.ws.state.remove_connection", new=AsyncMock()),
            patch("app.api.routers.ws.state.get_snapshot", new=AsyncMock(return_value={"type": "snapshot"})),
            patch("app.api.routers.ws.shared.get_recent_notifications", new=AsyncMock(return_value=[])),
            patch("app.api.routers.ws.db_session", side_effect=lambda: _FakeDbSession()),
            patch("app.api.routers.ws.ws.handle_ws_disconnect", new=AsyncMock()),
            patch("app.api.routers.ws.ws.route_ws_message", new=AsyncMock()) as route_ws_message,
        ):
            await ws_api_router.websocket_events(websocket)

        route_ws_message.assert_not_awaited()
        protocol_error = {
            "type": "protocol_error",
            "detail": "Malformed websocket frame: expected object with non-empty string 'type'.",
            "message_type": "",
        }
        self.assertIn(((protocol_error,), {}), websocket.send_json.await_args_list)

    async def test_ping_message_does_not_open_db_session_in_loop(self) -> None:
        websocket = AsyncMock()
        websocket.headers = {}
        websocket.query_params = {}
        websocket.receive_json = AsyncMock(side_effect=[{"type": "ping"}, WebSocketDisconnect(1000)])

        db_session_calls = 0

        def _db_factory():
            nonlocal db_session_calls
            db_session_calls += 1
            return _FakeDbSession()

        with (
            patch("app.api.routers.ws.should_enforce_local_auth", return_value=False),
            patch("app.api.routers.ws.state.add_connection", new=AsyncMock()),
            patch("app.api.routers.ws.state.remove_connection", new=AsyncMock()),
            patch("app.api.routers.ws.state.get_snapshot", new=AsyncMock(return_value={"type": "snapshot"})),
            patch("app.api.routers.ws.shared.get_recent_notifications", new=AsyncMock(return_value=[])),
            patch("app.api.routers.ws.db_session", side_effect=_db_factory),
            patch("app.api.routers.ws.ws.handle_ws_disconnect", new=AsyncMock()),
            patch("app.api.routers.ws.ws.route_ws_message", new=AsyncMock(return_value=0)) as route_ws_message,
        ):
            await ws_api_router.websocket_events(websocket)

        # One DB session is expected for initial snapshot fetch only.
        self.assertEqual(db_session_calls, 1)
        route_ws_message.assert_awaited_once_with(websocket, {"type": "ping"}, None, 0)


if __name__ == "__main__":
    unittest.main()
