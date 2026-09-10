import json
import shutil
import unittest
from datetime import date, datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.services.daily_summary import DailySummaryService


class FakeMessagesClient:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return type("Message", (), {"sid": "SM123"})()


class FakeTwilioClient:
    def __init__(self):
        self.messages = FakeMessagesClient()


class DailySummaryTests(unittest.TestCase):
    def setUp(self):
        self.temp_root = (
            Path("tests") / ".tmp_daily_summary" / f"{self._testMethodName}_{uuid4().hex}"
        )
        self.log_dir = self.temp_root / "logs"
        self.history_path = self.temp_root / "history.json"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.twilio_client = FakeTwilioClient()
        self.service = DailySummaryService(
            log_dir=self.log_dir,
            history_path=self.history_path,
            timezone_name="Europe/Helsinki",
            to_phone="+358400000000",
            from_phone="+14780000000",
            twilio_client=self.twilio_client,
        )

    def tearDown(self):
        shutil.rmtree(self.temp_root, ignore_errors=True)

    def test_build_digest_summarizes_matching_day(self):
        self._write_session(
            "session_one.json",
            ended_at="2026-05-18T12:30:00+00:00",
            direction="outbound",
            to_number="+358401111111",
            duration_seconds=300,
            turns=[
                {"speaker": "user", "text": "I want to book a room for June."},
                {"speaker": "assistant", "text": "I can check availability for you right away."},
            ],
        )
        self._write_session(
            "session_two.json",
            ended_at="2026-05-18T14:00:00+00:00",
            direction="outbound",
            to_number="+358402222222",
            duration_seconds=120,
            turns=[
                {"speaker": "user", "text": "What is the price and can I bring a pet?"},
                {"speaker": "assistant", "text": "Pets are not allowed."},
            ],
        )
        self._write_session(
            "session_three.json",
            ended_at="2026-05-17T20:00:00+00:00",
            direction="outbound",
            to_number="+358403333333",
            duration_seconds=30,
            turns=[
                {"speaker": "user", "text": "Old day should not be included."},
            ],
        )

        digest = self.service.build_digest(summary_date=self._local_date("2026-05-18"))

        self.assertEqual(digest.total_activities, 2)
        self.assertEqual(digest.completed_activities, 2)
        self.assertIn("booking", digest.topic_counts)
        self.assertIn("pricing", digest.topic_counts)
        self.assertIn("Nostot:", digest.sms_body)
        self.assertIn("+358401111111", digest.sms_body)

    def test_booking_words_with_false_recorded_signal_do_not_mark_reservation_made(self):
        self._write_session(
            "session_booking_words_no_reservation.json",
            ended_at="2026-05-18T13:00:00+00:00",
            direction="outbound",
            to_number="+358404444444",
            duration_seconds=90,
            turns=[
                {"speaker": "user", "text": "I want to book a room, do you have availability?"},
                {"speaker": "assistant", "text": "Let me check availability for you."},
            ],
        )

        digest = self.service.build_digest(summary_date=self._local_date("2026-05-18"))

        self.assertEqual(digest.total_activities, 1)
        self.assertNotIn("varaus tehty", digest.activities[0].highlight)

    def test_send_digest_records_history_and_prevents_duplicate_send(self):
        self._write_session(
            "session_one.json",
            ended_at="2026-05-18T09:15:00+00:00",
            direction="outbound",
            to_number="+358401111111",
            duration_seconds=180,
            turns=[
                {"speaker": "user", "text": "Please check availability for a booking."},
                {"speaker": "assistant", "text": "I can help with that."},
            ],
        )
        summary_date = self._local_date("2026-05-18")

        first_result = self.service.send_digest(summary_date)
        second_result = self.service.send_digest(summary_date)

        self.assertTrue(first_result.sent)
        self.assertEqual(first_result.message_sid, "SM123")
        self.assertFalse(second_result.sent)
        self.assertEqual(second_result.skipped_reason, "already_sent")
        self.assertEqual(len(self.twilio_client.messages.calls), 1)

        history = json.loads(self.history_path.read_text(encoding="utf-8"))
        self.assertIn("2026-05-18", history)

    def test_digest_can_use_anonymized_summary_without_raw_dialogue_turns(self):
        payload = {
            "call_sid": "session_masked",
            "stream_sid": "session_masked",
            "status": "completed",
            "created_at": "2026-05-18T10:00:00+00:00",
            "started_at": "2026-05-18T10:00:00+00:00",
            "ended_at": "2026-05-18T10:04:00+00:00",
            "duration_seconds": 240,
            "termination_reason": "twilio_stop",
            "last_error": None,
            "metadata": {
                "direction": "outbound",
                "counterparty_label": "***1234",
            },
            "anonymized_summary": {
                "summary": "Asiakas kysyi kesäkuun puolivälin varauksesta ja sai varauslinkin.",
                "caller_intent": "Lyhyttä majoitusta koskeva varauskysely.",
                "outcome": "Saatavuus vahvistettiin ja varauslinkki jaettiin.",
                "topics": ["varaus", "saatavuus"],
                "follow_up_needed": False,
                "reservation_created": True,
                "first_user_utterance_redacted": "Asiakas tarvitsi huoneen kesäkuun puoliväliin.",
                "redaction_notes": ["päivämäärä yleistetty"],
                "anonymization_method": "openai_llm",
            },
            "raw_transcript_persisted": False,
        }
        (self.log_dir / "session_masked.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        digest = self.service.build_digest(summary_date=self._local_date("2026-05-18"))

        self.assertEqual(digest.total_activities, 1)
        self.assertEqual(digest.activities[0].counterparty, "***1234")
        self.assertIn("booking", digest.activities[0].topics)
        self.assertIn("***1234", digest.sms_body)

    def test_build_last_24h_digest_uses_rolling_window(self):
        self._write_session(
            "session_before_window.json",
            ended_at="2026-05-19T04:59:00+03:00",
            direction="outbound",
            to_number="+358400000001",
            duration_seconds=90,
            turns=[{"speaker": "user", "text": "Outside the rolling window."}],
        )
        self._write_session(
            "session_inside_window_one.json",
            ended_at="2026-05-19T08:15:00+03:00",
            direction="outbound",
            to_number="+358400000002",
            duration_seconds=210,
            turns=[{"speaker": "user", "text": "Need a booking for tomorrow."}],
        )
        self._write_session(
            "session_inside_window_two.json",
            ended_at="2026-05-20T07:59:00+03:00",
            direction="outbound",
            to_number="+358400000003",
            duration_seconds=60,
            turns=[{"speaker": "user", "text": "Is there parking available?"}],
        )

        digest = self.service.build_last_24h_digest(
            window_end=datetime(2026, 5, 20, 8, 0, tzinfo=ZoneInfo("Europe/Helsinki"))
        )

        self.assertEqual(digest.total_activities, 2)
        self.assertEqual(digest.window_start, "2026-05-19T08:00:00+03:00")
        self.assertEqual(digest.window_end, "2026-05-20T08:00:00+03:00")
        self.assertIn("viimeiset 24 h", digest.sms_body)
        self.assertIn("+358400000002", digest.sms_body)
        self.assertIn("+358400000003", digest.sms_body)

    def test_send_digest_skips_sms_when_there_are_no_activities(self):
        result = self.service.send_digest(self._local_date("2026-05-18"))

        self.assertFalse(result.sent)
        self.assertEqual(result.skipped_reason, "no_activities")
        self.assertEqual(len(self.twilio_client.messages.calls), 0)

    def test_send_last_24h_digest_records_distinct_history_key(self):
        window_end = datetime(2026, 5, 20, 8, 0, tzinfo=ZoneInfo("Europe/Helsinki"))
        self._write_session(
            "session_inside_window.json",
            ended_at="2026-05-19T12:00:00+03:00",
            direction="outbound",
            to_number="+358400000004",
            duration_seconds=180,
            turns=[{"speaker": "user", "text": "Please send booking details."}],
        )

        first_result = self.service.send_last_24h_digest(window_end=window_end)
        second_result = self.service.send_last_24h_digest(window_end=window_end)

        self.assertTrue(first_result.sent)
        self.assertEqual(
            first_result.history_key,
            "rolling_24h:2026-05-20T08:00:00+03:00",
        )
        self.assertFalse(second_result.sent)
        self.assertEqual(second_result.skipped_reason, "already_sent")
        self.assertEqual(len(self.twilio_client.messages.calls), 1)

        history = json.loads(self.history_path.read_text(encoding="utf-8"))
        self.assertIn("rolling_24h:2026-05-20T08:00:00+03:00", history)

    def _write_session(
        self,
        filename: str,
        *,
        ended_at: str,
        direction: str,
        to_number: str,
        duration_seconds: float,
        turns: list[dict[str, str]],
    ) -> None:
        payload = {
            "call_sid": filename,
            "stream_sid": filename,
            "status": "completed",
            "created_at": ended_at,
            "started_at": ended_at,
            "ended_at": ended_at,
            "duration_seconds": duration_seconds,
            "termination_reason": "twilio_stop",
            "last_error": None,
            "metadata": {
                "direction": direction,
                "to_number": to_number,
            },
            "dialogue_turns": turns,
        }
        (self.log_dir / filename).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _local_date(raw_value: str):
        return date.fromisoformat(raw_value)
