from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.models.call import utc_now_iso

logger = logging.getLogger(__name__)

LIVE_STATUS_RINGING = "ringing"
LIVE_STATUS_CONNECTED = "connected"
LIVE_STATUS_IN_PROGRESS = "in_progress"
LIVE_STATUS_ENDED = "ended"
LIVE_STATUS_ERROR = "error"

LIVE_QUEUE_MAXSIZE = 64


class LiveBroadcastHub:
    def __init__(self, *, queue_maxsize: int = LIVE_QUEUE_MAXSIZE) -> None:
        self._queue_maxsize = queue_maxsize
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._last_status: dict[str, Any] | None = None

    def register(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self._queue_maxsize)
        self._subscribers.add(queue)
        return queue

    def unregister(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(queue)

    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def publish(self, event: dict[str, Any]) -> None:
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(
                    "Dropped live broadcast event for a full subscriber queue event_type=%s",
                    event.get("type"),
                )

    def publish_status(self, state: str, *, reason: str | None = None) -> None:
        event = {
            "type": "status",
            "ts": utc_now_iso(),
            "state": state,
            "reason": reason,
        }
        self._last_status = event
        self.publish(event)

    def state_snapshot(self) -> dict[str, Any]:
        return {"status": self._last_status}

    def reset_call_state(self) -> None:
        self._last_status = None


live_broadcast_hub = LiveBroadcastHub()
