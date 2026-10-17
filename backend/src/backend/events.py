"""In-process pub/sub feeding the laptop's SSE stream, one queue per session."""

from __future__ import annotations

import asyncio
import json
from typing import Any

# A laptop that stops reading must not stall uploads, so slow subscribers lose the
# oldest events instead of blocking the publisher. They recover via the next snapshot.
QUEUE_MAXSIZE = 256
KEEPALIVE_SECONDS = 15.0

CREATED = "asset.created"
STORED = "asset.stored"
READY = "asset.ready"
FAILED = "asset.failed"
REMOVED = "asset.removed"
SNAPSHOT = "snapshot"

# Process-button job lifecycle (see processing.py).
JOB_STARTED = "job.started"
JOB_PROGRESS = "job.progress"
JOB_DONE = "job.done"
JOB_FAILED = "job.failed"


class Broker:
    def __init__(self) -> None:
        self._subs: dict[str, set[asyncio.Queue]] = {}

    def subscribe(self, session_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_MAXSIZE)
        self._subs.setdefault(session_id, set()).add(queue)
        return queue

    def unsubscribe(self, session_id: str, queue: asyncio.Queue) -> None:
        subscribers = self._subs.get(session_id)
        if subscribers is None:
            return
        subscribers.discard(queue)
        if not subscribers:
            del self._subs[session_id]

    def subscriber_count(self, session_id: str) -> int:
        return len(self._subs.get(session_id, ()))

    async def publish(self, session_id: str, event: str, data: dict[str, Any]) -> None:
        for queue in tuple(self._subs.get(session_id, ())):
            if queue.full():
                queue.get_nowait()
            queue.put_nowait({"event": event, "data": data})


def sse_frame(event: str, payload: dict[str, Any] | None = None) -> dict[str, str]:
    frame = {"event": event}
    if payload is not None:
        frame["data"] = json.dumps(payload)
    return frame