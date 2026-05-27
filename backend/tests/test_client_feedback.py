import unittest
from unittest.mock import AsyncMock

from app.services.interaction.client_feedback import feedback_processing


class ClientFeedbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_feedback_processing_ignores_close_state_runtime_error_on_exit(self) -> None:
        websocket = AsyncMock()
        websocket.send_json = AsyncMock(
            side_effect=[
                None,
                RuntimeError('Cannot call "send" once a close message has been sent.'),
            ]
        )

        async with feedback_processing(websocket, active=True):
            pass

        self.assertEqual(websocket.send_json.await_count, 2)


if __name__ == "__main__":
    unittest.main()
