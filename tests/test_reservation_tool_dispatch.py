import json
import shutil
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from app.models.call import CallConfig, CallSession
from app.services import realtime_tools
from app.services.realtime_session import CREATE_RESERVATION_TOOL_NAME
from app.services.realtime_tools import execute_realtime_tool
from app.services.synthetic_reservation_store import SyntheticReservationStore

UNIT_ID = "jokipuistopark-asunto-2"  # capacity=4, nightly_rate_eur=138, min_nights=1
UNIT_NIGHTLY_RATE = 138


def _future_date(days_ahead: int = 10) -> str:
    return (date.today() + timedelta(days=days_ahead)).isoformat()


class ReservationToolDispatchTests(unittest.IsolatedAsyncioTestCase):
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

    def tearDown(self):
        self.patcher.stop()
        shutil.rmtree(self.temp_root, ignore_errors=True)

    def _new_session(self) -> CallSession:
        return CallSession(call_sid="CA_test", config=CallConfig())

    async def test_confirmed_reservation_writes_record_and_reads_back(self):
        arrival = _future_date()
        session = self._new_session()

        result = await execute_realtime_tool(
            CREATE_RESERVATION_TOOL_NAME,
            json.dumps({"arrivalDate": arrival, "nights": 2, "guests": 2, "unitId": UNIT_ID}),
            session=session,
        )

        self.assertEqual(result["status"], "confirmed")
        self.assertTrue(result["demo_reservation"])
        self.assertEqual(result["source"], "synthetic_reservation_store")
        reservation = result["reservation"]
        self.assertIsNotNone(reservation)
        self.assertTrue(reservation["reservation_id"].isupper())
        self.assertEqual(reservation["price_total"], 2 * UNIT_NIGHTLY_RATE)

        on_disk = json.loads(self.store_path.read_text())
        self.assertEqual(len(on_disk["reservations"]), 1)
        self.assertEqual(on_disk["reservations"][0]["reservation_id"], reservation["reservation_id"])

        active = self.store.list_active_reservations()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].reservation_id, reservation["reservation_id"])

    async def test_duplicate_dispatch_same_unit_and_dates_is_already_reserved(self):
        arrival = _future_date()
        session = self._new_session()
        args = json.dumps({"arrivalDate": arrival, "nights": 2, "guests": 2, "unitId": UNIT_ID})

        first = await execute_realtime_tool(CREATE_RESERVATION_TOOL_NAME, args, session=session)
        self.assertEqual(first["status"], "confirmed")

        second = await execute_realtime_tool(CREATE_RESERVATION_TOOL_NAME, args, session=session)
        self.assertEqual(second["status"], "already_reserved_for_stay")

        on_disk = json.loads(self.store_path.read_text())
        self.assertEqual(len(on_disk["reservations"]), 1)

    async def test_session_none_refuses_dispatch_with_session_unavailable(self):
        result = await execute_realtime_tool(
            CREATE_RESERVATION_TOOL_NAME,
            json.dumps({"arrivalDate": _future_date(), "nights": 2, "guests": 2, "unitId": UNIT_ID}),
            session=None,
        )

        self.assertEqual(result["status"], "invalid_request")
        self.assertEqual(result["error_code"], "session_unavailable")
        self.assertFalse(self.store_path.exists())

    async def test_overlapping_stay_for_same_unit_is_unavailable(self):
        arrival = date.today() + timedelta(days=10)
        args_one = json.dumps(
            {
                "arrivalDate": arrival.isoformat(),
                "nights": 3,
                "guests": 2,
                "unitId": UNIT_ID,
            }
        )
        args_two = json.dumps(
            {
                "arrivalDate": (arrival + timedelta(days=1)).isoformat(),
                "nights": 3,
                "guests": 2,
                "unitId": UNIT_ID,
            }
        )

        first = await execute_realtime_tool(
            CREATE_RESERVATION_TOOL_NAME, args_one, session=self._new_session()
        )
        self.assertEqual(first["status"], "confirmed")

        second = await execute_realtime_tool(
            CREATE_RESERVATION_TOOL_NAME, args_two, session=self._new_session()
        )
        self.assertEqual(second["status"], "unavailable")

        on_disk = json.loads(self.store_path.read_text())
        self.assertEqual(len(on_disk["reservations"]), 1)

    async def test_unknown_unit_id_returns_unit_not_found_and_writes_nothing(self):
        result = await execute_realtime_tool(
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

        self.assertEqual(result["status"], "unit_not_found")
        self.assertFalse(self.store_path.exists())

    async def test_invalid_requests_return_invalid_request_and_write_nothing(self):
        invalid_payloads = [
            {"arrivalDate": _future_date(), "nights": 0, "guests": 2, "unitId": UNIT_ID},
            {"arrivalDate": _future_date(), "nights": 61, "guests": 2, "unitId": UNIT_ID},
            {"arrivalDate": _future_date(), "nights": 2, "guests": 0, "unitId": UNIT_ID},
            {"arrivalDate": _future_date(), "nights": 2, "guests": 31, "unitId": UNIT_ID},
            {"arrivalDate": "not-a-date", "nights": 2, "guests": 2, "unitId": UNIT_ID},
            {
                "arrivalDate": (date.today() - timedelta(days=1)).isoformat(),
                "nights": 2,
                "guests": 2,
                "unitId": UNIT_ID,
            },
        ]

        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                result = await execute_realtime_tool(
                    CREATE_RESERVATION_TOOL_NAME,
                    json.dumps(payload),
                    session=self._new_session(),
                )
                self.assertEqual(result["status"], "invalid_request")
                self.assertTrue(result["message_for_assistant"])
                self.assertFalse(self.store_path.exists())

    async def test_guests_above_capacity_is_unavailable(self):
        result = await execute_realtime_tool(
            CREATE_RESERVATION_TOOL_NAME,
            json.dumps(
                {
                    "arrivalDate": _future_date(),
                    "nights": 2,
                    "guests": 5,
                    "unitId": UNIT_ID,
                }
            ),
            session=self._new_session(),
        )

        self.assertEqual(result["status"], "unavailable")
        self.assertFalse(self.store_path.exists())

    async def test_nights_below_min_nights_is_unavailable(self):
        # hostelli-framinranta has min_nights=2
        result = await execute_realtime_tool(
            CREATE_RESERVATION_TOOL_NAME,
            json.dumps(
                {
                    "arrivalDate": _future_date(),
                    "nights": 1,
                    "guests": 1,
                    "unitId": "hostelli-framinranta",
                }
            ),
            session=self._new_session(),
        )

        self.assertEqual(result["status"], "unavailable")
        self.assertFalse(self.store_path.exists())

    async def test_written_record_carries_no_caller_identifying_data(self):
        result = await execute_realtime_tool(
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
        self.assertEqual(result["status"], "confirmed")

        on_disk = json.loads(self.store_path.read_text())
        record_keys = set(on_disk["reservations"][0].keys())
        forbidden_keys = {"phone", "caller_name", "guest_name", "transcript"}
        self.assertEqual(record_keys & forbidden_keys, set())


if __name__ == "__main__":
    unittest.main()
