import unittest
from datetime import datetime, timezone

from app.core import websocket_state
from app.schemas import AgentStatus


class WebsocketStateTests(unittest.IsolatedAsyncioTestCase):
    async def test_set_and_get_status_roundtrip(self) -> None:
        new_status = AgentStatus(
            state="running",
            detail="unit-test",
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

        await websocket_state.set_status(new_status)
        current = await websocket_state.get_status()

        self.assertEqual(current.state, "running")
        self.assertEqual(current.detail, "unit-test")

    async def test_snapshot_contains_status_payload(self) -> None:
        snapshot = await websocket_state.get_snapshot([])

        self.assertEqual(snapshot.get("type"), "snapshot")
        self.assertIn("status", snapshot)
        self.assertEqual(snapshot.get("notifications"), [])


if __name__ == "__main__":
    unittest.main()
