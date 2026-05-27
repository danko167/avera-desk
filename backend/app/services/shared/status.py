from datetime import datetime, timezone

from ...core import websocket_state as app_state
from ...schemas import AgentState, AgentStatus


async def set_status(state_value: AgentState, detail: str) -> None:
    """Update agent status and broadcast to all clients."""
    status = AgentStatus(
        state=state_value,
        detail=detail,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    updated_status = await app_state.set_status(status)
    await app_state.broadcast(
        {"type": "status", "status": updated_status.model_dump()}
    )


__all__ = ["set_status"]