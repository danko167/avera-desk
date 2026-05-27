import asyncio
from datetime import datetime, timezone
import logging
from typing import Any

from starlette.websockets import WebSocketDisconnect
from fastapi import WebSocket

from ..schemas import AgentStatus, Notification

# Global state
logger = logging.getLogger(__name__)

_agent_status = AgentStatus(
    state="standby",
    detail="No active agent jobs",
    updated_at=datetime.now(timezone.utc).isoformat(),
)
_connections: set[WebSocket] = set()
_connections_lock = asyncio.Lock()
_status_lock = asyncio.Lock()


async def add_connection(websocket: WebSocket) -> None:
    """Register a new WebSocket connection."""
    async with _connections_lock:
        _connections.add(websocket)


async def remove_connection(websocket: WebSocket) -> None:
    """Unregister a WebSocket connection."""
    async with _connections_lock:
        _connections.discard(websocket)


async def broadcast(payload: dict) -> None:
    """Send a message to all connected clients."""
    async with _connections_lock:
        targets = list(_connections)

    async def send_to_connection(connection: WebSocket) -> WebSocket | None:
        try:
            await connection.send_json(payload)
            return None
        except (WebSocketDisconnect, RuntimeError) as exc:
            logger.debug("ws_broadcast_connection_stale error=%s", exc)
            return connection

    stale = [
        connection
        for connection in await asyncio.gather(*(send_to_connection(connection) for connection in targets))
        if connection is not None
    ]

    if stale:
        async with _connections_lock:
            for connection in stale:
                _connections.discard(connection)


async def get_snapshot(notifications: list[Notification]) -> dict[str, Any]:
    """Build a snapshot payload from the given notification list."""
    async with _status_lock:
        status_payload = _agent_status.model_dump()
    return {
        "type": "snapshot",
        "status": status_payload,
        "notifications": [n.model_dump() for n in notifications],
    }


async def get_status() -> AgentStatus:
    """Get current agent status."""
    async with _status_lock:
        return _agent_status.model_copy(deep=True)


async def set_status(status: AgentStatus) -> AgentStatus:
    """Set and return current agent status under lock."""
    global _agent_status
    async with _status_lock:
        _agent_status = status
        return _agent_status.model_copy(deep=True)
