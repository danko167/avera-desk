from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ..core.logging import configure_logging, get_logger
from ..db import init_db
from ..services import workers

# Configure logging at app startup.
configure_logging(level=logging.INFO)
logger = get_logger(__name__)

_sync_task: asyncio.Task | None = None
_reminder_task: asyncio.Task | None = None


async def _cancel_task(task: asyncio.Task | None, task_name: str) -> None:
    if task is None:
        return

    if task.done():
        logger.info("%s already finished before shutdown", task_name)
        return

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        logger.info("%s cancelled during shutdown", task_name)
    else:
        logger.info("%s exited cleanly after cancellation request", task_name)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await init_db()

    global _sync_task, _reminder_task
    _sync_task = asyncio.create_task(workers.run_email_sync_worker())
    _reminder_task = asyncio.create_task(workers.run_speech_reminder_worker(logger))

    yield

    await _cancel_task(_sync_task, "email sync worker")
    await _cancel_task(_reminder_task, "speech reminder worker")
