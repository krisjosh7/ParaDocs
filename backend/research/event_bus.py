"""
In-memory SSE event bus for research pipeline live streaming.

Graph nodes publish events via `emit(case_id, event)`.
SSE endpoint subscribes via `subscribe(case_id)` → AsyncGenerator.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

# case_id → list of asyncio.Queue subscribers
_subscribers: dict[str, list[asyncio.Queue]] = {}
_lock = asyncio.Lock()


async def subscribe(case_id: str) -> asyncio.Queue:
    """Register a new subscriber queue for a case's research events."""
    async with _lock:
        if case_id not in _subscribers:
            _subscribers[case_id] = []
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        _subscribers[case_id].append(q)
        return q


async def unsubscribe(case_id: str, q: asyncio.Queue) -> None:
    """Remove a subscriber queue."""
    async with _lock:
        subs = _subscribers.get(case_id)
        if subs and q in subs:
            subs.remove(q)
        if subs is not None and len(subs) == 0:
            _subscribers.pop(case_id, None)


def emit(case_id: str, event: dict[str, Any]) -> None:
    """
    Publish an event to all subscribers for a case.
    Safe to call from sync or async contexts (non-blocking put_nowait).
    """
    event.setdefault("ts", time.time())
    subs = _subscribers.get(case_id)
    if not subs:
        return
    payload = json.dumps(event)
    for q in list(subs):
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            pass  # drop if client is too slow
