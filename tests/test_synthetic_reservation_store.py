import asyncio
import json
import shutil
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from app.models.call import CallConfig, CallSession
from app.services.synthetic_reservation_store import SyntheticReservationStore

UNIT_ID = "jokipuistopark-asunto-2"  # capacity=4, nightly_rate_eur=138, min_nights=1


def _future_date(days_ahead: int = 10) -> str:
    return (date.today() + timedelta(days=days_ahead)).isoformat()


def _iso_ago(seconds: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()


class SyntheticReservationStoreTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_root = Path("tests") / ".tmp_synthetic_reservation_store"
        self.temp_root.mkdir(parents=True, exist_ok=True)
        self.store_path = self.temp_root / f"{self._testMethodName}_{uuid4().hex}.json"

    def tearDown(self):
        shutil.rmtree(self.temp_root, ignore_errors=True)

    def _seed(self, reservations: list[dict]) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self.store_path.write_text(
            json.dumps({"reservations": reservations}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _make_store(self, *, ttl_hours: float = 24.0, max_per_call: int = 3) -> SyntheticReservationStore:
        return SyntheticReservationStore(
            storage_path=self.store_path,
            ttl=timedelta(hours=ttl_hours),
            max_per_call=max_per_call,
        )

    async def test_expired_reservation_is_absent_and_does_not_block_overlap(self):
        expired_record = {
            "reservation_id": "OLD12345",
            "unit_id": UNIT_ID,
            "unit_name": "Jokipuistopark asunto 2",
            "area": "Jokipuisto",
            "arrival_date": _future_date(5),
            "departure_date": _future_date(7),
            "nights": 2,
            "guests": 2,
            "price_total": 276,
            "currency": "EUR",
            "created_at": _iso_ago(3600),
            "expires_at": _iso_ago(1),
        }
        self._seed([expired_record])
        store = self._make_store()

        active = store.list_active_reservations()
        self.assertEqual(active, [])

        result = await store.create_reservation(
            {
                "arrivalDate": _future_date(5),
                "nights": 2,
                "guests": 2,
                "unitId": UNIT_ID,
            }
        )

        self.assertEqual(result.status, "confirmed")
        on_disk = json.loads(self.store_path.read_text())
        self.assertEqual(len(on_disk["reservations"]), 1)
        self.assertEqual(on_disk["reservations"][0]["reservation_id"], result.reservation.reservation_id)

    async def test_ttl_boundary_is_exclusive(self):
        store = self._make_store(ttl_hours=0.0)

        result = await store.create_reservation(
            {
                "arrivalDate": _future_date(),
                "nights": 2,
                "guests": 2,
                "unitId": UNIT_ID,
            }
        )
        self.assertEqual(result.status, "confirmed")

        # With ttl=0, expires_at == created_at; by the time this assertion runs,
        # real elapsed time has already pushed "now" to or past expires_at, so the
        # record must be considered expired, not active (exclusive boundary).
        active = store.list_active_reservations()
        self.assertEqual(active, [])

    async def test_prune_on_write_drops_expired_and_keeps_active(self):
        expired_record = {
            "reservation_id": "EXPIRED1",
            "unit_id": "kampusaukio-7-asunto-1",
            "unit_name": "Kampusaukio 7, asunto 1",
            "area": "Kampusaukio",
            "arrival_date": _future_date(1),
            "departure_date": _future_date(3),
            "nights": 2,
            "guests": 2,
            "price_total": 298,
            "currency": "EUR",
            "created_at": _iso_ago(7200),
            "expires_at": _iso_ago(3600),
        }
        active_record = {
            "reservation_id": "ACTIVE01",
            "unit_id": "kampusaukio-7-asunto-2",
            "unit_name": "Kampusaukio 7, asunto 2",
            "area": "Kampusaukio",
            "arrival_date": _future_date(1),
            "departure_date": _future_date(3),
            "nights": 2,
            "guests": 2,
            "price_total": 230,
            "currency": "EUR",
            "created_at": _iso_ago(60),
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        }
        self._seed([expired_record, active_record])
        store = self._make_store()

        result = await store.create_reservation(
            {
                "arrivalDate": _future_date(5),
                "nights": 2,
                "guests": 2,
                "unitId": UNIT_ID,
            }
        )
        self.assertEqual(result.status, "confirmed")

        on_disk = json.loads(self.store_path.read_text())
        persisted_ids = {record["reservation_id"] for record in on_disk["reservations"]}
        self.assertEqual(
            persisted_ids,
            {"ACTIVE01", result.reservation.reservation_id},
        )

    async def test_concurrent_overlapping_create_persists_exactly_one_record(self):
        store = self._make_store()
        arrival = date.today() + timedelta(days=20)
        payload_one = {
            "arrivalDate": arrival.isoformat(),
            "nights": 3,
            "guests": 2,
            "unitId": UNIT_ID,
        }
        payload_two = {
            "arrivalDate": (arrival + timedelta(days=1)).isoformat(),
            "nights": 3,
            "guests": 2,
            "unitId": UNIT_ID,
        }

        result_one, result_two = await asyncio.gather(
            store.create_reservation(payload_one),
            store.create_reservation(payload_two),
        )

        statuses = sorted([result_one.status, result_two.status])
        self.assertEqual(statuses, ["confirmed", "unavailable"])

        on_disk = json.loads(self.store_path.read_text())
        self.assertEqual(len(on_disk["reservations"]), 1)

    async def test_duplicate_stay_in_same_session_is_already_reserved_and_no_second_write(self):
        store = self._make_store()
        session = CallSession(call_sid="CA_dup", config=CallConfig())
        payload = {
            "arrivalDate": _future_date(),
            "nights": 2,
            "guests": 2,
            "unitId": UNIT_ID,
        }

        first = await store.create_reservation(payload, session=session)
        self.assertEqual(first.status, "confirmed")

        second = await store.create_reservation(payload, session=session)
        self.assertEqual(second.status, "already_reserved_for_stay")

        on_disk = json.loads(self.store_path.read_text())
        self.assertEqual(len(on_disk["reservations"]), 1)

    async def test_history_records_reservation_fields(self):
        store = self._make_store()
        session = CallSession(call_sid="CA_hist", config=CallConfig())
        payload = {
            "arrivalDate": _future_date(),
            "nights": 2,
            "guests": 2,
            "unitId": UNIT_ID,
        }

        result = await store.create_reservation(payload, session=session)
        self.assertEqual(result.status, "confirmed")

        history = session.metadata["create_reservation_history"]
        self.assertEqual(len(history), 1)
        entry = history[0]
        self.assertEqual(entry["reservation_id"], result.reservation.reservation_id)
        self.assertEqual(entry["unit_id"], UNIT_ID)
        self.assertIn("arrival_date", entry)
        self.assertIn("departure_date", entry)
        self.assertIn("created_at", entry)

    async def test_session_none_creates_reservation_without_history_or_cap(self):
        store = self._make_store(max_per_call=1)

        first = await store.create_reservation(
            {
                "arrivalDate": _future_date(1),
                "nights": 2,
                "guests": 2,
                "unitId": "kampusaukio-7-asunto-1",
            }
        )
        second = await store.create_reservation(
            {
                "arrivalDate": _future_date(5),
                "nights": 2,
                "guests": 2,
                "unitId": "kampusaukio-7-asunto-2",
            }
        )

        self.assertEqual(first.status, "confirmed")
        self.assertEqual(second.status, "confirmed")
        on_disk = json.loads(self.store_path.read_text())
        self.assertEqual(len(on_disk["reservations"]), 2)

    async def test_cap_reached_rejects_further_reservation_for_different_unit(self):
        store = self._make_store(max_per_call=1)
        session = CallSession(call_sid="CA_cap", config=CallConfig())

        first = await store.create_reservation(
            {
                "arrivalDate": _future_date(1),
                "nights": 2,
                "guests": 2,
                "unitId": "kampusaukio-7-asunto-1",
            },
            session=session,
        )
        self.assertEqual(first.status, "confirmed")

        second = await store.create_reservation(
            {
                "arrivalDate": _future_date(5),
                "nights": 2,
                "guests": 2,
                "unitId": "kampusaukio-7-asunto-2",
            },
            session=session,
        )

        self.assertEqual(second.status, "already_reserved_for_stay")
        self.assertEqual(second.error_code, "reservation_cap_reached")
        on_disk = json.loads(self.store_path.read_text())
        self.assertEqual(len(on_disk["reservations"]), 1)


class SyntheticReservationStoreAvailabilityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_root = Path("tests") / ".tmp_synthetic_reservation_store"
        self.temp_root.mkdir(parents=True, exist_ok=True)
        self.store_path = self.temp_root / f"{self._testMethodName}_{uuid4().hex}.json"

    def tearDown(self):
        shutil.rmtree(self.temp_root, ignore_errors=True)

    def _seed(self, reservations: list[dict]) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self.store_path.write_text(
            json.dumps({"reservations": reservations}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _make_store(self, *, ttl_hours: float = 24.0, max_per_call: int = 3) -> SyntheticReservationStore:
        return SyntheticReservationStore(
            storage_path=self.store_path,
            ttl=timedelta(hours=ttl_hours),
            max_per_call=max_per_call,
        )

    async def test_available_unit_by_id_returns_priced_option(self):
        store = self._make_store()
        response = await store.check_availability(
            {
                "arrivalDate": _future_date(10),
                "nights": 3,
                "guests": 2,
                "unitId": UNIT_ID,
            }
        )

        self.assertEqual(response.source, "synthetic_reservation_store")
        self.assertEqual(response.status, "available")
        self.assertEqual(len(response.options), 1)
        option = response.options[0]
        self.assertEqual(option.status, "available")
        self.assertEqual(option.price_total, 3 * 138)
        self.assertTrue(response.booking_not_confirmed)

    async def test_no_unit_selector_and_any_area_returns_one_option_per_unit(self):
        store = self._make_store()
        response = await store.check_availability(
            {
                "arrivalDate": _future_date(10),
                "nights": 2,
                "guests": 2,
                "area": "any",
            }
        )

        self.assertEqual(response.status, "available")
        self.assertGreater(len(response.options), 1)

    async def test_area_filter_returns_only_that_area_units(self):
        store = self._make_store()
        response = await store.check_availability(
            {
                "arrivalDate": _future_date(10),
                "nights": 2,
                "guests": 2,
                "area": "Jokipuisto",
            }
        )

        self.assertTrue(response.options)
        self.assertTrue(all(option.area == "Jokipuisto" for option in response.options))

    async def test_unit_name_resolves_via_fuzzy_matcher(self):
        store = self._make_store()
        response = await store.check_availability(
            {
                "arrivalDate": _future_date(10),
                "nights": 2,
                "guests": 2,
                "unitName": "Jokipuistopark asunto 2",
            }
        )

        self.assertEqual(len(response.options), 1)
        self.assertEqual(response.options[0].unit_id, "jokipuistopark-asunto-2")

    async def test_active_reservation_blocks_stay_then_frees_after_ttl(self):
        blocking_arrival = _future_date(10)
        blocking_departure = _future_date(12)
        blocked_record = {
            "reservation_id": "BLOCK123",
            "unit_id": UNIT_ID,
            "unit_name": "Jokipuistopark asunto 2",
            "area": "Jokipuisto",
            "arrival_date": blocking_arrival,
            "departure_date": blocking_departure,
            "nights": 2,
            "guests": 2,
            "price_total": 276,
            "currency": "EUR",
            "created_at": _iso_ago(3600),
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        }
        self._seed([blocked_record])
        store = self._make_store()

        blocked_response = await store.check_availability(
            {
                "arrivalDate": blocking_arrival,
                "nights": 2,
                "guests": 2,
                "unitId": UNIT_ID,
            }
        )
        self.assertEqual(blocked_response.options[0].status, "unavailable")

        expired_record = dict(blocked_record)
        expired_record["expires_at"] = _iso_ago(1)
        self._seed([expired_record])

        freed_response = await store.check_availability(
            {
                "arrivalDate": blocking_arrival,
                "nights": 2,
                "guests": 2,
                "unitId": UNIT_ID,
            }
        )
        self.assertEqual(freed_response.options[0].status, "available")

    async def test_guests_above_capacity_is_guest_count_unavailable(self):
        store = self._make_store()
        response = await store.check_availability(
            {
                "arrivalDate": _future_date(10),
                "nights": 2,
                "guests": 10,
                "unitId": UNIT_ID,
            }
        )
        self.assertEqual(response.options[0].status, "guest_count_unavailable")

    async def test_nights_below_minimum_is_duration_unavailable_with_free_durations(self):
        store = self._make_store()
        response = await store.check_availability(
            {
                "arrivalDate": _future_date(10),
                "nights": 1,
                "guests": 2,
                "unitId": "ranta-hostelli",
            }
        )
        option = response.options[0]
        self.assertEqual(option.status, "duration_unavailable")
        self.assertTrue(option.available_durations)
        self.assertTrue(all(duration.nights >= 2 for duration in option.available_durations))

    async def test_arrival_date_yesterday_is_not_selectable(self):
        store = self._make_store()
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        response = await store.check_availability(
            {
                "arrivalDate": yesterday,
                "nights": 2,
                "guests": 2,
                "unitId": UNIT_ID,
            }
        )
        self.assertEqual(response.options[0].status, "not_selectable")

    async def test_unknown_unit_id_yields_unit_not_found(self):
        store = self._make_store()
        response = await store.check_availability(
            {
                "arrivalDate": _future_date(10),
                "nights": 2,
                "guests": 2,
                "unitId": "does-not-exist",
            }
        )
        self.assertEqual(response.status, "unknown")
        self.assertEqual(response.error_code, "unit_not_found")
        self.assertEqual(response.options, [])

    async def test_malformed_arrival_date_raises_validation_error(self):
        store = self._make_store()
        from app.models.reservation import ReservationValidationError

        with self.assertRaises(ReservationValidationError):
            await store.check_availability(
                {
                    "arrivalDate": "not-a-date",
                    "nights": 2,
                    "guests": 2,
                    "unitId": UNIT_ID,
                }
            )

    async def test_every_response_carries_booking_not_confirmed_true(self):
        store = self._make_store()
        response = await store.check_availability(
            {
                "arrivalDate": _future_date(10),
                "nights": 2,
                "guests": 2,
                "unitId": UNIT_ID,
            }
        )
        self.assertTrue(response.booking_not_confirmed)


if __name__ == "__main__":
    unittest.main()
