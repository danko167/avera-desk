from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import WebSocket
from sqlalchemy.ext.asyncio import AsyncSession

from . import client_feedback
from ..shared.outcome import ServiceExecutionOutcome


async def execute_service_interaction(
    websocket: WebSocket,
    db: AsyncSession,
    *,
    show_processing: bool,
    operation: Callable[[], Awaitable[ServiceExecutionOutcome]],
) -> ServiceExecutionOutcome:
    async with client_feedback.feedback_processing(
        websocket,
        active=show_processing,
    ):
        outcome = await operation()

    await client_feedback.apply_client_interaction_outcome(
        websocket,
        db,
        outcome=outcome.interaction,
    )
    return outcome