from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.models.call import utc_now_iso
from app.services.live_redactor import redact_for_broadcast
from app.services.realtime_session import (
    AVAILABILITY_TOOL_NAME,
    CALLBACK_REQUEST_SMS_TOOL_NAME,
    CREATE_RESERVATION_TOOL_NAME,
)

logger = logging.getLogger(__name__)

LIVE_STATUS_RINGING = "ringing"
LIVE_STATUS_CONNECTED = "connected"
LIVE_STATUS_IN_PROGRESS = "in_progress"
LIVE_STATUS_ENDED = "ended"
LIVE_STATUS_ERROR = "error"

LIVE_QUEUE_MAXSIZE = 64

# Allow-list of stay-detail argument keys that may ever be projected into a
# public agent-state event. Any argument key not named here is dropped by
# construction — a deny-list would silently leak a future tool schema's key.
LIVE_SLOT_KEYS: tuple[str, ...] = (
    "arrivalDate",
    "nights",
    "guests",
    "area",
    "unitName",
    "unitId",
)

TOOL_INTENTS: dict[str, dict[str, str]] = {
    AVAILABILITY_TOOL_NAME: {
        "intent": "Tarkistaa saatavuutta",
        "step": "availability_check",
    },
    CREATE_RESERVATION_TOOL_NAME: {
        "intent": "Tekee varausta",
        "step": "reservation_create",
    },
    CALLBACK_REQUEST_SMS_TOOL_NAME: {
        "intent": "Välittää soittopyyntöä",
        "step": "callback_request",
    },
}

CAPABILITY_EXAMPLES: list[dict[str, str]] = [
    {
        "tool": AVAILABILITY_TOOL_NAME,
        "example_phrase": "Miten voin varata huoneen?",
    },
    {
        "tool": CREATE_RESERVATION_TOOL_NAME,
        "example_phrase": "Kyllä kiitos.",
    },
    {
        "tool": CALLBACK_REQUEST_SMS_TOOL_NAME,
        "example_phrase": "Maksu ei onnistu, mitä teen?",
    },
]


class LiveBroadcastHub:
    def __init__(self, *, queue_maxsize: int = LIVE_QUEUE_MAXSIZE) -> None:
        self._queue_maxsize = queue_maxsize
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._last_status: dict[str, Any] | None = None
        self._agent_intent: str | None = None
        self._agent_step: str | None = None
        self._agent_slots: dict[str, str] = {}
        self._fired_capabilities: list[str] = []

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
        if state == LIVE_STATUS_RINGING:
            self.reset_call_state()

        event = {
            "type": "status",
            "ts": utc_now_iso(),
            "state": state,
            "reason": reason,
        }
        self._last_status = event
        self.publish(event)

    def publish_transcript(self, *, speaker: str, text: str) -> None:
        redacted_text = redact_for_broadcast(text).strip()
        if not redacted_text:
            return

        event = {
            "type": "transcript",
            "ts": utc_now_iso(),
            "speaker": speaker,
            "text": redacted_text,
        }
        self.publish(event)

    def publish_agent_state(self, *, tool: str, arguments: dict[str, Any]) -> None:
        tool_intent = TOOL_INTENTS.get(tool)
        if tool_intent is None:
            return

        for key in LIVE_SLOT_KEYS:
            value = arguments.get(key)
            if value in (None, ""):
                continue
            self._agent_slots[key] = str(value)

        self._agent_intent = tool_intent["intent"]
        self._agent_step = tool_intent["step"]

        event = {
            "type": "agent",
            "ts": utc_now_iso(),
            "intent": self._agent_intent,
            "step": self._agent_step,
            "slots": dict(self._agent_slots),
        }
        self.publish(event)

    def publish_capability(self, *, tool: str) -> None:
        if tool not in TOOL_INTENTS:
            return

        if tool not in self._fired_capabilities:
            self._fired_capabilities.append(tool)

        event = {
            "type": "capability",
            "ts": utc_now_iso(),
            "tool": tool,
        }
        self.publish(event)

    def state_snapshot(self) -> dict[str, Any]:
        return {
            "status": self._last_status,
            "agent": {
                "intent": self._agent_intent,
                "step": self._agent_step,
                "slots": dict(self._agent_slots),
            },
            "capabilities": list(self._fired_capabilities),
        }

    def reset_call_state(self) -> None:
        self._last_status = None
        self._agent_intent = None
        self._agent_step = None
        self._agent_slots = {}
        self._fired_capabilities = []


live_broadcast_hub = LiveBroadcastHub()
