import asyncio
from typing import Optional

from .collectors.binance_collector import run_collector_loop

_stop_event: Optional[asyncio.Event] = None
_task: Optional[asyncio.Task] = None


async def on_startup():
    global _stop_event, _task
    _stop_event = asyncio.Event()
    _task = asyncio.create_task(run_collector_loop(_stop_event))


async def on_shutdown():
    global _stop_event, _task
    if _stop_event is not None:
        _stop_event.set()
    if _task is not None:
        try:
            await asyncio.wait_for(_task, timeout=5)
        except asyncio.TimeoutError:
            _task.cancel()
