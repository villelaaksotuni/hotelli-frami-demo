import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.daily_summary_scheduler import DailySummaryScheduler


class FakeSummaryService:
    def __init__(self):
        self.calls = []

    def send_last_24h_digest(self, *, window_end):
        self.calls.append(window_end)
        return type(
            "Result",
            (),
            {
                "sent": True,
                "skipped_reason": None,
                "activities_found": 2,
            },
        )()


class DailySummarySchedulerTests(unittest.TestCase):
    def setUp(self):
        self.timezone = ZoneInfo("Europe/Helsinki")
        self.summary_service = FakeSummaryService()
        self.scheduler = DailySummaryScheduler(
            summary_service=self.summary_service,
            timezone_name="Europe/Helsinki",
            send_time="08:00",
        )

    def test_latest_due_window_end_is_none_before_send_time(self):
        due = self.scheduler.latest_due_window_end(
            datetime(2026, 5, 20, 7, 59, tzinfo=self.timezone)
        )

        self.assertIsNone(due)

    def test_latest_due_window_end_uses_todays_8am_after_send_time(self):
        due = self.scheduler.latest_due_window_end(
            datetime(2026, 5, 20, 10, 15, tzinfo=self.timezone)
        )

        self.assertEqual(due, datetime(2026, 5, 20, 8, 0, tzinfo=self.timezone))

    def test_next_run_after_rolls_to_next_day_after_send_time(self):
        next_run = self.scheduler.next_run_after(
            datetime(2026, 5, 20, 10, 15, tzinfo=self.timezone)
        )

        self.assertEqual(next_run, datetime(2026, 5, 21, 8, 0, tzinfo=self.timezone))

    def test_send_due_digest_passes_scheduled_window_end_to_service(self):
        result = self.scheduler.send_due_digest(
            now=datetime(2026, 5, 20, 9, 0, tzinfo=self.timezone)
        )

        self.assertTrue(result.sent)
        self.assertEqual(len(self.summary_service.calls), 1)
        self.assertEqual(
            self.summary_service.calls[0],
            datetime(2026, 5, 20, 8, 0, tzinfo=self.timezone),
        )


if __name__ == "__main__":
    unittest.main()
