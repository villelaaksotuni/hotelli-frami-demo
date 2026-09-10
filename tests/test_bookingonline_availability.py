import unittest
from datetime import date
from pathlib import Path

from app.services.availability_checker import BookingOnlineAvailabilityChecker
from app.services.bookingonline_parser import parse_calendar_html, parse_eur_price

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def fixture(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


class FakeFetcher:
    def __init__(self, html: str) -> None:
        self.html = html
        self.calls = []

    async def fetch_calendar_html(self, unit, *, arrival_date: date, guests: int) -> str:
        self.calls.append((unit.unitId, arrival_date, guests))
        return self.html


class BookingOnlineAvailabilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_selectable_date_matching_guests_and_duration_is_available(self):
        checker = BookingOnlineAvailabilityChecker(
            fetcher=FakeFetcher(fixture("selectable_calendar.html"))
        )

        result = await checker.check(
            {
                "arrivalDate": "2026-05-16",
                "nights": 8,
                "guests": 4,
                "unitId": "jokipuistopark-asunto-2",
            }
        )

        payload = result.to_dict()
        self.assertEqual(payload["status"], "available")
        self.assertTrue(payload["booking_not_confirmed"])
        self.assertEqual(payload["options"][0]["price_total"], 1012)
        self.assertEqual(payload["options"][0]["tuote_id"], "9202-51004")
        self.assertIn("kiintea_tuote_id=51004", payload["options"][0]["calendar_url"])
        self.assertIn("kesto=8", payload["options"][0]["booking_url"])
        self.assertIn("tuote_id=9202-51004", payload["options"][0]["booking_url"])

    async def test_kielletty_date_is_not_selectable(self):
        checker = BookingOnlineAvailabilityChecker(
            fetcher=FakeFetcher(fixture("blocked_calendar.html"))
        )

        result = await checker.check(
            {
                "arrivalDate": "2026-05-16",
                "nights": 8,
                "guests": 4,
                "unitId": "jokipuistopark-asunto-2",
            }
        )

        self.assertEqual(result.status, "not_selectable")
        self.assertEqual(result.options[0].status, "not_selectable")

    async def test_missing_guest_count_returns_guest_count_unavailable(self):
        checker = BookingOnlineAvailabilityChecker(
            fetcher=FakeFetcher(fixture("missing_guest_calendar.html"))
        )

        result = await checker.check(
            {
                "arrivalDate": "2026-05-16",
                "nights": 8,
                "guests": 4,
                "unitId": "jokipuistopark-asunto-2",
            }
        )

        self.assertEqual(result.status, "guest_count_unavailable")
        self.assertEqual(result.options[0].available_durations[0].price_total, 1012)

    async def test_missing_requested_duration_returns_available_alternatives(self):
        checker = BookingOnlineAvailabilityChecker(
            fetcher=FakeFetcher(fixture("duration_alternatives_calendar.html"))
        )

        result = await checker.check(
            {
                "arrivalDate": "2026-05-16",
                "nights": 8,
                "guests": 4,
                "unitId": "jokipuistopark-asunto-2",
            }
        )

        self.assertEqual(result.status, "duration_unavailable")
        self.assertEqual([item.nights for item in result.options[0].available_durations], [2, 3])

    async def test_multiple_units_are_checked_for_area(self):
        fake_fetcher = FakeFetcher(fixture("selectable_calendar.html"))
        checker = BookingOnlineAvailabilityChecker(fetcher=fake_fetcher)

        result = await checker.check(
            {
                "arrivalDate": "2026-05-16",
                "nights": 8,
                "guests": 4,
                "area": "Kampusaukio",
            }
        )

        self.assertEqual(result.status, "available")
        self.assertGreaterEqual(len(result.options), 2)
        self.assertGreaterEqual(len(fake_fetcher.calls), 2)

    async def test_unit_name_resolves_specific_named_property(self):
        fake_fetcher = FakeFetcher(fixture("selectable_calendar.html"))
        checker = BookingOnlineAvailabilityChecker(fetcher=fake_fetcher)

        result = await checker.check(
            {
                "arrivalDate": "2026-05-16",
                "nights": 8,
                "guests": 4,
                "unitName": "Jokipuistopark asunto 2",
            }
        )

        self.assertEqual(result.status, "available")
        self.assertEqual(len(result.options), 1)
        self.assertEqual(result.options[0].unit_id, "jokipuistopark-asunto-2")
        self.assertEqual(fake_fetcher.calls[0][0], "jokipuistopark-asunto-2")

    async def test_unit_name_with_area_disambiguates_generic_apartment_name(self):
        fake_fetcher = FakeFetcher(fixture("selectable_calendar.html"))
        checker = BookingOnlineAvailabilityChecker(fetcher=fake_fetcher)

        result = await checker.check(
            {
                "arrivalDate": "2026-05-16",
                "nights": 8,
                "guests": 4,
                "area": "Kampusaukio",
                "unitName": "asunto 2",
            }
        )

        self.assertEqual(result.status, "available")
        self.assertEqual(len(result.options), 1)
        self.assertEqual(result.options[0].unit_id, "kampusaukio-7-asunto-2")
        self.assertEqual(fake_fetcher.calls[0][0], "kampusaukio-7-asunto-2")

    async def test_ambiguous_unit_name_without_area_checks_all_best_matches(self):
        fake_fetcher = FakeFetcher(fixture("selectable_calendar.html"))
        checker = BookingOnlineAvailabilityChecker(fetcher=fake_fetcher)

        result = await checker.check(
            {
                "arrivalDate": "2026-05-16",
                "nights": 8,
                "guests": 4,
                "unitName": "asunto 2",
            }
        )

        self.assertEqual(result.status, "available")
        self.assertEqual(
            {option.unit_id for option in result.options},
            {"jokipuistopark-asunto-2", "kampusaukio-7-asunto-2"},
        )
        self.assertEqual(
            {call[0] for call in fake_fetcher.calls},
            {"jokipuistopark-asunto-2", "kampusaukio-7-asunto-2"},
        )

    async def test_missing_changed_html_returns_unknown(self):
        checker = BookingOnlineAvailabilityChecker(
            fetcher=FakeFetcher(fixture("changed_schema.html"))
        )

        result = await checker.check(
            {
                "arrivalDate": "2026-05-16",
                "nights": 8,
                "guests": 4,
                "unitId": "jokipuistopark-asunto-2",
            }
        )

        self.assertEqual(result.status, "unknown")
        self.assertEqual(result.error_code, "calendar_uninterpretable")


class BookingOnlineParserTests(unittest.TestCase):
    def test_price_parsing_accepts_spaces_and_nbsp(self):
        self.assertEqual(parse_eur_price("8 vrk, 1 012 €"), 1012)
        self.assertEqual(parse_eur_price("8 vrk, 1\xa0012 €"), 1012)
        self.assertEqual(parse_eur_price("2 vrk, 262 €"), 262)

    def test_booking_url_action_is_extracted(self):
        page = parse_calendar_html(fixture("selectable_calendar.html"))

        self.assertEqual(page.product_name, "Jokipuistopark asunto 2, Jokipuisto")
        self.assertIsNotNone(page.booking_form_action)
        self.assertIn("VarausSv", page.booking_form_action)


if __name__ == "__main__":
    unittest.main()
