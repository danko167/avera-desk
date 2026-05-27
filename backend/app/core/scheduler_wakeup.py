from __future__ import annotations

import asyncio

_wakeup_event: asyncio.Event | None = None
_wakeup_loop: asyncio.AbstractEventLoop | None = None


def _get_wakeup_event() -> asyncio.Event:
    global _wakeup_event, _wakeup_loop

    loop = asyncio.get_running_loop()
    if _wakeup_event is None or _wakeup_loop is not loop:
        _wakeup_event = asyncio.Event()
        _wakeup_loop = loop
    return _wakeup_event


def notify_scheduler_wakeup() -> None:
    _get_wakeup_event().set()


async def wait_for_scheduler_wakeup(timeout_seconds: float) -> None:
    if timeout_seconds <= 0:
        return

    event = _get_wakeup_event()
    try:
        await asyncio.wait_for(event.wait(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        return
    event.clear()