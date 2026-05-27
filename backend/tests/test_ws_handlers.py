import unittest
from unittest.mock import AsyncMock, patch

from app.services.ws import handlers


class WsHandlersTests(unittest.IsolatedAsyncioTestCase):
    async def test_handle_audio_blob_invalid_bytes_reports_protocol_error(self) -> None:
        websocket = AsyncMock()
        websocket.send_json = AsyncMock()

        class _FakeTranscriber:
            def __init__(self) -> None:
                self.trace = None

            async def append_audio(self, _audio_b64: str, _chunk_bytes: int) -> None:
                return None

            async def maybe_commit_live(self) -> None:
                return None

        original_live_transcribers = handlers._live_transcribers.copy()
        handlers._live_transcribers[id(websocket)] = _FakeTranscriber()
        try:
            result = await handlers.handle_audio_blob(
                websocket,
                {
                    "type": "audio_blob",
                    "audio_base64": "Zm9v",
                    "bytes": "not-an-int",
                },
                session_audio_bytes=123,
            )
        finally:
            handlers._live_transcribers.clear()
            handlers._live_transcribers.update(original_live_transcribers)

        self.assertEqual(result, 123)
        websocket.send_json.assert_awaited_once_with(
            {
                "type": "protocol_error",
                "detail": "Audio chunk byte size must be an integer.",
                "message_type": "audio_blob",
            }
        )

    async def test_handle_ws_disconnect_resets_status(self) -> None:
        websocket = object()

        with patch("app.services.ws.handlers.status.set_status", new=AsyncMock()) as set_status:
            await handlers.handle_ws_disconnect(websocket)

        set_status.assert_awaited_once_with("standby", "No active agent jobs")


if __name__ == "__main__":
    unittest.main()
