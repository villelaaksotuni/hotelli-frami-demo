import inspect
import json
import shutil
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from app.models.call import CallConfig, CallSession
from app.services import realtime_tools
from app.services.live_broadcast import (
    CAPABILITY_EXAMPLES,
    LIVE_SLOT_KEYS,
    LIVE_STATUS_ENDED,
    LIVE_STATUS_RINGING,
    TOOL_INTENTS,
    LiveBroadcastHub,
    live_broadcast_hub,
)
from app.services.realtime_session import (
    AVAILABILITY_TOOL_NAME,
    CALLBACK_REQUEST_SMS_TOOL_NAME,
    CREATE_RESERVATION_TOOL_NAME,
)
from app.services.realtime_tools import execute_realtime_tool
from app.services.synthetic_reservation_store import SyntheticReservationStore

UNIT_ID = "jokipuistopark-asunto-2"


def _future_date(days_ahead: int = 10) -> str:
    return (date.today() + timedelta(days=days_ahead)).isoformat()


class LiveAgentStateHubTests(unittest.TestCase):
    """Direct hub-level tests against a fresh instance (not the singleton)."""

    def test_publish_agent_state_projects_only_allow_listed_keys(self):
        hub = LiveBroadcastHub()
        queue = hub.register()

        hub.publish_agent_state(
            tool=AVAILABILITY_TOOL_NAME,
            arguments={
                "arrivalDate": "2026-10-01",
                "nights": 2,
                "guests": 2,
                "secretNote": "should never appear",
            },
        )

        event = queue.get_nowait()
        serialized = json.dumps(event)
        self.assertNotIn("secretNote", serialized)
        self.assertNotIn("should never appear", serialized)
        self.assertEqual(event["slots"]["arrivalDate"], "2026-10-01")

    def test_slots_accumulate_across_dispatches_without_wiping_earlier_fields(self):
        hub = LiveBroadcastHub()
        queue = hub.register()

        hub.publish_agent_state(
            tool=AVAILABILITY_TOOL_NAME,
            arguments={"arrivalDate": "2026-10-01", "nights": 2, "guests": 2},
        )
        queue.get_nowait()

        hub.publish_agent_state(
            tool=CREATE_RESERVATION_TOOL_NAME,
            arguments={"unitId": UNIT_ID},
        )
        event = queue.get_nowait()

        self.assertEqual(event["slots"]["arrivalDate"], "2026-10-01")
        self.assertEqual(event["slots"]["unitId"], UNIT_ID)

    def test_callback_sms_tool_contributes_no_slots_but_still_publishes_intent_and_step(self):
        hub = LiveBroadcastHub()
        queue = hub.register()

        hub.publish_agent_state(
            tool=CALLBACK_REQUEST_SMS_TOOL_NAME,
            arguments={"callerName": "Matti Meikäläinen", "reason": "maksu ei onnistu"},
        )

        event = queue.get_nowait()
        self.assertEqual(event["slots"], {})
        self.assertEqual(event["step"], "callback_request")
        serialized = json.dumps(event)
        self.assertNotIn("Matti", serialized)
        self.assertNotIn("maksu ei onnistu", serialized)

    def test_unknown_tool_publishes_neither_agent_nor_capability_event(self):
        hub = LiveBroadcastHub()
        queue = hub.register()

        hub.publish_agent_state(tool="not_a_real_tool", arguments={"arrivalDate": "2026-10-01"})
        hub.publish_capability(tool="not_a_real_tool")

        self.assertEqual(queue.qsize(), 0)

    def test_publish_capability_event_shape_and_fired_set(self):
        hub = LiveBroadcastHub()
        queue = hub.register()

        hub.publish_capability(tool=AVAILABILITY_TOOL_NAME)

        event = queue.get_nowait()
        self.assertEqual(set(event.keys()), {"type", "ts", "tool"})
        self.assertEqual(event["type"], "capability")
        self.assertEqual(event["tool"], AVAILABILITY_TOOL_NAME)
        self.assertIn(AVAILABILITY_TOOL_NAME, hub.state_snapshot()["capabilities"])

    def test_publish_capability_and_publish_agent_state_are_declared_synchronous(self):
        self.assertFalse(inspect.iscoroutinefunction(LiveBroadcastHub.publish_capability))
        self.assertFalse(inspect.iscoroutinefunction(LiveBroadcastHub.publish_agent_state))

    def test_state_snapshot_includes_agent_and_capabilities_keys(self):
        hub = LiveBroadcastHub()
        snapshot = hub.state_snapshot()
        self.assertIn("agent", snapshot)
        self.assertIn("capabilities", snapshot)

    def test_ringing_clears_accumulated_slots_and_fired_capabilities(self):
        hub = LiveBroadcastHub()
        hub.publish_capability(tool=AVAILABILITY_TOOL_NAME)
        hub.publish_agent_state(
            tool=AVAILABILITY_TOOL_NAME,
            arguments={"arrivalDate": "2026-10-01"},
        )

        hub.publish_status(LIVE_STATUS_RINGING)
        snapshot = hub.state_snapshot()
        self.assertEqual(snapshot["capabilities"], [])
        self.assertEqual(snapshot["agent"]["slots"], {})

    def test_ended_leaves_slots_and_capabilities_intact(self):
        hub = LiveBroadcastHub()
        hub.publish_capability(tool=AVAILABILITY_TOOL_NAME)
        hub.publish_agent_state(
            tool=AVAILABILITY_TOOL_NAME,
            arguments={"arrivalDate": "2026-10-01"},
        )

        hub.publish_status(LIVE_STATUS_ENDED)
        snapshot = hub.state_snapshot()
        self.assertEqual(snapshot["capabilities"], [AVAILABILITY_TOOL_NAME])
        self.assertEqual(snapshot["agent"]["slots"]["arrivalDate"], "2026-10-01")

    def test_live_slot_keys_allow_list_excludes_pii_keys(self):
        self.assertNotIn("callerName", LIVE_SLOT_KEYS)
        self.assertNotIn("reason", LIVE_SLOT_KEYS)
        self.assertEqual(len(LIVE_SLOT_KEYS), 6)


class LiveAgentStateDispatchTests(unittest.IsolatedAsyncioTestCase):
    """Drives execute_realtime_tool through the real dispatch branches, observing
    events published to the module singleton live_broadcast_hub."""

    def setUp(self):
        self.temp_root = Path("tests") / ".tmp_reservation_store"
        self.temp_root.mkdir(parents=True, exist_ok=True)
        self.store_path = self.temp_root / f"{self._testMethodName}_{uuid4().hex}.json"
        self.store = SyntheticReservationStore(
            storage_path=self.store_path,
            ttl=timedelta(hours=24),
            max_per_call=3,
        )
        self.patcher = patch.object(realtime_tools, "reservation_provider", self.store)
        self.patcher.start()
        self.queue = live_broadcast_hub.register()

    def tearDown(self):
        self.patcher.stop()
        live_broadcast_hub.unregister(self.queue)
        live_broadcast_hub.reset_call_state()
        shutil.rmtree(self.temp_root, ignore_errors=True)

    def _new_session(self) -> CallSession:
        return CallSession(call_sid="CA_test", config=CallConfig())

    def _drain_events(self):
        events = []
        while not self.queue.empty():
            events.append(self.queue.get_nowait())
        return events

    async def test_availability_dispatch_publishes_agent_event_with_step_and_slots(self):
        arrival = _future_date()
        await execute_realtime_tool(
            AVAILABILITY_TOOL_NAME,
            json.dumps({"arrivalDate": arrival, "nights": 2, "guests": 2}),
            session=self._new_session(),
        )

        events = self._drain_events()
        agent_events = [e for e in events if e["type"] == "agent"]
        self.assertEqual(len(agent_events), 1)
        self.assertEqual(agent_events[0]["step"], "availability_check")
        self.assertEqual(agent_events[0]["slots"]["arrivalDate"], arrival)
        self.assertEqual(agent_events[0]["slots"]["nights"], "2")
        self.assertEqual(agent_events[0]["slots"]["guests"], "2")

    async def test_slots_persist_across_availability_then_create_reservation_dispatch(self):
        arrival = _future_date()
        session = self._new_session()

        await execute_realtime_tool(
            AVAILABILITY_TOOL_NAME,
            json.dumps({"arrivalDate": arrival, "nights": 2, "guests": 2}),
            session=session,
        )
        self._drain_events()

        await execute_realtime_tool(
            CREATE_RESERVATION_TOOL_NAME,
            json.dumps(
                {
                    "arrivalDate": arrival,
                    "nights": 2,
                    "guests": 2,
                    "unitId": UNIT_ID,
                }
            ),
            session=session,
        )
        events = self._drain_events()
        agent_events = [e for e in events if e["type"] == "agent"]
        self.assertEqual(len(agent_events), 1)
        self.assertEqual(agent_events[0]["slots"]["arrivalDate"], arrival)
        self.assertEqual(agent_events[0]["slots"]["unitId"], UNIT_ID)

    async def test_unrecognized_argument_key_never_reaches_published_event(self):
        arrival = _future_date()
        await execute_realtime_tool(
            AVAILABILITY_TOOL_NAME,
            json.dumps(
                {
                    "arrivalDate": arrival,
                    "nights": 2,
                    "guests": 2,
                    "secretNote": "never publish this",
                }
            ),
            session=self._new_session(),
        )

        events = self._drain_events()
        serialized = json.dumps(events)
        self.assertNotIn("secretNote", serialized)
        self.assertNotIn("never publish this", serialized)

    async def test_callback_sms_dispatch_publishes_capability_and_agent_without_pii(self):
        session = self._new_session()
        await execute_realtime_tool(
            CALLBACK_REQUEST_SMS_TOOL_NAME,
            json.dumps({"callerName": "Matti Meikäläinen", "reason": "maksu ei onnistu"}),
            session=session,
        )

        events = self._drain_events()
        self.assertTrue(any(e["type"] == "capability" for e in events))
        self.assertTrue(any(e["type"] == "agent" for e in events))
        serialized = json.dumps(events)
        for forbidden in (
            "callerName",
            "caller_name",
            "caller_phone",
            "owner_phone",
            "reason",
            "Matti",
            "maksu ei onnistu",
        ):
            self.assertNotIn(forbidden, serialized)

    async def test_each_tool_publishes_capability_event_with_exact_keys(self):
        arrival = _future_date()
        session = self._new_session()

        await execute_realtime_tool(
            AVAILABILITY_TOOL_NAME,
            json.dumps({"arrivalDate": arrival, "nights": 2, "guests": 2}),
            session=session,
        )
        await execute_realtime_tool(
            CREATE_RESERVATION_TOOL_NAME,
            json.dumps(
                {
                    "arrivalDate": arrival,
                    "nights": 2,
                    "guests": 2,
                    "unitId": UNIT_ID,
                }
            ),
            session=session,
        )
        await execute_realtime_tool(
            CALLBACK_REQUEST_SMS_TOOL_NAME,
            json.dumps({"reason": "urgent"}),
            session=session,
        )

        events = self._drain_events()
        capability_events = [e for e in events if e["type"] == "capability"]
        self.assertEqual(len(capability_events), 3)
        for event in capability_events:
            self.assertEqual(set(event.keys()), {"type", "ts", "tool"})
        tools_seen = {e["tool"] for e in capability_events}
        self.assertEqual(
            tools_seen,
            {AVAILABILITY_TOOL_NAME, CREATE_RESERVATION_TOOL_NAME, CALLBACK_REQUEST_SMS_TOOL_NAME},
        )

    async def test_fired_capability_appears_in_state_snapshot_for_mid_call_joiner(self):
        await execute_realtime_tool(
            AVAILABILITY_TOOL_NAME,
            json.dumps({"arrivalDate": _future_date(), "nights": 2, "guests": 2}),
            session=self._new_session(),
        )

        snapshot = live_broadcast_hub.state_snapshot()
        self.assertIn(AVAILABILITY_TOOL_NAME, snapshot["capabilities"])

    async def test_unknown_tool_name_publishes_no_capability_or_agent_event(self):
        await execute_realtime_tool(
            "not_a_real_tool",
            json.dumps({}),
            session=self._new_session(),
        )

        events = self._drain_events()
        self.assertEqual(events, [])

    async def test_create_reservation_refused_dispatch_does_not_light_capability(self):
        await execute_realtime_tool(
            CREATE_RESERVATION_TOOL_NAME,
            json.dumps(
                {
                    "arrivalDate": _future_date(),
                    "nights": 2,
                    "guests": 2,
                    "unitId": UNIT_ID,
                }
            ),
            session=None,
        )

        events = self._drain_events()
        self.assertEqual(events, [])


class CapabilityExamplesConstantTests(unittest.TestCase):
    def test_capability_examples_has_three_entries_with_tool_and_phrase_keys(self):
        self.assertEqual(len(CAPABILITY_EXAMPLES), 3)
        for entry in CAPABILITY_EXAMPLES:
            self.assertEqual(set(entry.keys()), {"tool", "example_phrase"})

    def test_capability_examples_tools_match_tool_intents_keys(self):
        example_tools = {entry["tool"] for entry in CAPABILITY_EXAMPLES}
        self.assertEqual(example_tools, set(TOOL_INTENTS.keys()))


if __name__ == "__main__":
    unittest.main()
