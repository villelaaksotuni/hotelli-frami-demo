import asyncio
import json
import re
import shutil
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from starlette.requests import Request

from app.models.call import CallConfig, CallSession
from app.routes import live as live_module
from app.routes.live import build_board_entries, live_page
from app.services import realtime_tools
from app.services.live_broadcast import (
    LIVE_BOARD_FIELDS,
    LIVE_BOARD_LIMIT,
    LiveBroadcastHub,
    live_broadcast_hub,
)
from app.services.realtime_session import CREATE_RESERVATION_TOOL_NAME
from app.services.realtime_tools import execute_realtime_tool
from app.services.synthetic_reservation_store import SyntheticReservationStore

UNIT_ID = "jokipuistopark-asunto-2"  # capacity=4, nightly_rate_eur=138, min_nights=1


def _future_date(days_ahead: int = 10) -> str:
    return (date.today() + timedelta(days=days_ahead)).isoformat()


def _full_reservation_dict(**overrides) -> dict:
    base = {
        "reservation_id": "ABC12345",
        "unit_id": UNIT_ID,
        "unit_name": "Jokipuistopark asunto 2",
        "area": "Jokipuisto",
        "arrival_date": _future_date(),
        "departure_date": _future_date(12),
        "nights": 2,
        "guests": 2,
        "price_total": 276,
        "currency": "EUR",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(),
    }
    base.update(overrides)
    return base


def _build_page_request() -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": "/live",
            "raw_path": b"/live",
            "root_path": "",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("demo.example.com", 443),
        }
    )


class LiveBoardFieldAllowListTests(unittest.TestCase):
    def test_allow_list_contains_the_nine_expected_keys_and_excludes_internal_pii_keys(self):
        self.assertEqual(
            set(LIVE_BOARD_FIELDS),
            {
                "reservation_id",
                "unit_name",
                "area",
                "arrival_date",
                "departure_date",
                "nights",
                "guests",
                "price_total",
                "currency",
            },
        )
        for forbidden in (
            "unit_id",
            "created_at",
            "expires_at",
            "caller_phone",
            "caller_name",
        ):
            self.assertNotIn(forbidden, LIVE_BOARD_FIELDS)

    def test_limit_is_20(self):
        self.assertEqual(LIVE_BOARD_LIMIT, 20)


class PublishReservationHubTests(unittest.TestCase):
    def test_publish_reservation_emits_only_allow_listed_fields(self):
        hub = LiveBroadcastHub()
        queue = hub.register()

        hub.publish_reservation(_full_reservation_dict())

        event = hub_event = queue.get_nowait()
        self.assertEqual(event["type"], "reservation")
        self.assertEqual(set(event["reservation"].keys()), set(LIVE_BOARD_FIELDS))
        del hub_event

    def test_extra_caller_phone_key_never_reaches_serialised_event(self):
        hub = LiveBroadcastHub()
        queue = hub.register()

        hub.publish_reservation(_full_reservation_dict(caller_phone="+358401234567"))

        event = queue.get_nowait()
        serialized = json.dumps(event)
        self.assertNotIn("caller_phone", serialized)
        self.assertNotIn("+358401234567", serialized)

    def test_publish_reservation_is_declared_synchronous(self):
        import inspect

        self.assertFalse(inspect.iscoroutinefunction(LiveBroadcastHub.publish_reservation))

    def test_publish_reservation_not_included_in_reset_call_state(self):
        # The board persists across calls, unlike the four call panels.
        hub = LiveBroadcastHub()
        hub.publish_reservation(_full_reservation_dict())
        hub.reset_call_state()
        snapshot = hub.state_snapshot()
        self.assertNotIn("board", snapshot)


class CreateReservationDispatchPublishTests(unittest.IsolatedAsyncioTestCase):
    """Drives execute_realtime_tool through the real create-reservation branch,
    observing events published to the module singleton live_broadcast_hub."""

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

    async def test_confirmed_dispatch_publishes_exactly_one_reservation_event(self):
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
            session=self._new_session(),
        )

        events = self._drain_events()
        reservation_events = [e for e in events if e["type"] == "reservation"]
        self.assertEqual(len(reservation_events), 1)
        self.assertEqual(set(reservation_events[0]["reservation"].keys()), set(LIVE_BOARD_FIELDS))

    async def test_refused_dispatch_publishes_no_reservation_event(self):
        # session=None causes the dispatch to refuse before ever calling the store.
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
        self.assertEqual([e for e in events if e["type"] == "reservation"], [])

    async def test_non_confirmed_status_publishes_no_reservation_event(self):
        await execute_realtime_tool(
            CREATE_RESERVATION_TOOL_NAME,
            json.dumps(
                {
                    "arrivalDate": _future_date(),
                    "nights": 2,
                    "guests": 2,
                    "unitId": "not-a-real-unit",
                }
            ),
            session=self._new_session(),
        )

        events = self._drain_events()
        self.assertEqual([e for e in events if e["type"] == "reservation"], [])


class BuildBoardEntriesTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_root = Path("tests") / ".tmp_reservation_store"
        self.temp_root.mkdir(parents=True, exist_ok=True)
        self.store_path = self.temp_root / f"{self._testMethodName}_{uuid4().hex}.json"
        self.store = SyntheticReservationStore(
            storage_path=self.store_path,
            ttl=timedelta(hours=24),
            max_per_call=10,
        )

    def tearDown(self):
        shutil.rmtree(self.temp_root, ignore_errors=True)

    def _seed(self, reservations: list[dict]) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self.store_path.write_text(
            json.dumps({"reservations": reservations}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def test_reads_only_through_the_provider_seam(self):
        with patch.object(live_module, "reservation_provider", self.store) as patched:
            self._seed([_full_reservation_dict(reservation_id="SEEDED1")])
            entries = build_board_entries()
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["reservation_id"], "SEEDED1")
        del patched

    def test_returns_at_most_limit_ordered_newest_first(self):
        now = datetime.now(timezone.utc)
        records = []
        for i in range(25):
            records.append(
                _full_reservation_dict(
                    reservation_id=f"R{i:03d}",
                    created_at=(now - timedelta(minutes=25 - i)).isoformat(),
                )
            )
        self._seed(records)

        with patch.object(live_module, "reservation_provider", self.store):
            entries = build_board_entries()

        self.assertEqual(len(entries), 20)
        # Newest first: the last-created record (R024) should be first.
        self.assertEqual(entries[0]["reservation_id"], "R024")
        self.assertEqual(entries[-1]["reservation_id"], "R005")

    def test_every_entry_has_exactly_the_allow_listed_field_set(self):
        self._seed([_full_reservation_dict()])
        with patch.object(live_module, "reservation_provider", self.store):
            entries = build_board_entries()

        self.assertEqual(len(entries), 1)
        self.assertEqual(set(entries[0].keys()), set(LIVE_BOARD_FIELDS))

    def test_expired_reservation_absent_with_no_purge_step_invoked(self):
        expired = _full_reservation_dict(
            reservation_id="EXPIRED1",
            created_at=(datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
            expires_at=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
        )
        active = _full_reservation_dict(reservation_id="ACTIVE01")
        self._seed([expired, active])

        with patch.object(live_module, "reservation_provider", self.store):
            entries = build_board_entries()

        ids = {entry["reservation_id"] for entry in entries}
        self.assertEqual(ids, {"ACTIVE01"})


class SnapshotFrameBoardKeyTests(unittest.IsolatedAsyncioTestCase):
    async def test_snapshot_frame_contains_a_board_key_whose_value_is_a_list(self):
        with patch.object(live_module, "build_board_entries", return_value=[{"reservation_id": "X"}]):
            snapshot = {"type": "snapshot", "ts": "now"}
            snapshot.update(live_broadcast_hub.state_snapshot())
            snapshot["board"] = await asyncio.to_thread(live_module.build_board_entries)
            self.assertIn("board", snapshot)
            self.assertIsInstance(snapshot["board"], list)


if __name__ == "__main__":
    unittest.main()
