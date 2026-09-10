import json
import shutil
import unittest
from pathlib import Path
from uuid import uuid4

from app.services.dashboard_data import DashboardDataService


class DashboardDataTests(unittest.TestCase):
    def setUp(self):
        self.temp_root = (
            Path("tests") / ".tmp_dashboard_data" / f"{self._testMethodName}_{uuid4().hex}"
        )
        self.log_dir = self.temp_root / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.service = DashboardDataService(
            log_dir=self.log_dir,
            timezone_name="Europe/Helsinki",
        )

    def tearDown(self):
        shutil.rmtree(self.temp_root, ignore_errors=True)

    def test_build_dashboard_payload_counts_resolved_and_unresolved_calls(self):
        self._write_session(
            "session_one.json",
            {
                "call_sid": "CA1",
                "stream_sid": "MZ1",
                "status": "completed",
                "created_at": "2026-05-20T06:00:00+00:00",
                "started_at": "2026-05-20T06:00:00+00:00",
                "ended_at": "2026-05-20T06:03:00+00:00",
                "duration_seconds": 180,
                "termination_reason": "twilio_stop",
                "last_error": None,
                "metadata": {
                    "direction": "inbound",
                    "counterparty_label": "***1111",
                },
                "anonymized_summary": {
                    "summary": "Asiakas tiedusteli majoitusta ja sai varauslinkin.",
                    "caller_intent": "Lyhyt varauskysely.",
                    "outcome": "Saatavuus vahvistettiin.",
                    "topics": ["booking", "availability"],
                    "follow_up_needed": False,
                    "reservation_created": True,
                    "first_user_utterance_redacted": "Tarvitsen huoneen ensi viikolle.",
                    "redaction_notes": [],
                    "anonymization_method": "openai_llm",
                },
                "analytics": {
                    "direction": "inbound",
                    "direction_label": "Saapuva",
                    "counterparty_label": "***1111",
                    "topics": ["booking", "availability"],
                    "topic_labels": ["Varaus", "Saatavuus"],
                    "follow_up_needed": False,
                    "reservation_created": True,
                    "has_error": False,
                    "resolution_status": "resolved",
                    "resolution_label": "Ratkaistu",
                    "summary_preview": "Asiakas tiedusteli majoitusta ja sai varauslinkin.",
                    "caller_intent": "Lyhyt varauskysely.",
                    "outcome": "Saatavuus vahvistettiin.",
                    "transcript_turn_count": 4,
                },
                "transcript_turn_count": 4,
            },
        )
        self._write_session(
            "session_two.json",
            {
                "call_sid": "CA2",
                "stream_sid": "MZ2",
                "status": "completed",
                "created_at": "2026-05-19T08:00:00+00:00",
                "started_at": "2026-05-19T08:00:00+00:00",
                "ended_at": "2026-05-19T08:01:30+00:00",
                "duration_seconds": 90,
                "termination_reason": "twilio_stop",
                "last_error": None,
                "metadata": {
                    "direction": "outbound",
                    "counterparty_label": "***2222",
                },
                "anonymized_summary": {
                    "summary": "Asiakas kysyi hinnoittelusta ja pyysi yhteydenottoa myöhemmin.",
                    "caller_intent": "Hintatiedustelu.",
                    "outcome": "Tarvitaan jatkotoimia.",
                    "topics": ["hinta"],
                    "follow_up_needed": True,
                    "reservation_created": False,
                    "first_user_utterance_redacted": "Paljonko yö maksaa?",
                    "redaction_notes": [],
                    "anonymization_method": "openai_llm",
                },
                "transcript_turn_count": 3,
            },
        )

        payload = self.service.build_dashboard_payload(
            now=self._dt("2026-05-20T12:00:00+03:00"),
        )

        self.assertEqual(payload["summary"]["total_calls"], 2)
        self.assertEqual(payload["summary"]["resolved_calls"], 1)
        self.assertEqual(payload["summary"]["unresolved_calls"], 1)
        self.assertEqual(payload["summary"]["follow_up_calls"], 1)
        self.assertEqual(payload["summary"]["reservation_calls"], 1)
        self.assertEqual(payload["summary"]["inbound_calls"], 1)
        self.assertEqual(payload["summary"]["outbound_calls"], 1)
        self.assertEqual(payload["summary"]["average_duration_seconds"], 135.0)
        self.assertEqual(payload["summary"]["resolution_rate"], 50.0)
        self.assertEqual(payload["recent_calls"][0]["resolution_label"], "Ratkaistu")
        self.assertEqual(payload["topic_breakdown"][0]["label"], "Varaus")

    def test_booking_words_in_dialogue_with_false_analytics_signal_are_not_counted(self):
        self._write_session(
            "session_booking_words_no_reservation.json",
            {
                "call_sid": "CA4",
                "stream_sid": "MZ4",
                "status": "completed",
                "created_at": "2026-05-20T09:00:00+00:00",
                "started_at": "2026-05-20T09:00:00+00:00",
                "ended_at": "2026-05-20T09:01:00+00:00",
                "duration_seconds": 60,
                "termination_reason": "twilio_stop",
                "last_error": None,
                "metadata": {
                    "direction": "inbound",
                    "counterparty_label": "***5555",
                    "reservation_created": False,
                },
                "dialogue_turns": [
                    {"speaker": "user", "text": "I would like to book a reservation, do you have a room?"},
                    {"speaker": "assistant", "text": "Let me check availability."},
                ],
                "transcript_turn_count": 2,
            },
        )

        payload = self.service.build_dashboard_payload(
            now=self._dt("2026-05-20T12:00:00+03:00"),
        )

        self.assertEqual(payload["summary"]["reservation_calls"], 0)
        self.assertFalse(payload["recent_calls"][0]["reservation_created"])

    def test_fixture_omitting_reservation_key_entirely_deserializes_with_signal_false(self):
        self._write_session(
            "session_no_reservation_key.json",
            {
                "call_sid": "CA5",
                "stream_sid": "MZ5",
                "status": "completed",
                "created_at": "2026-05-20T10:00:00+00:00",
                "started_at": "2026-05-20T10:00:00+00:00",
                "ended_at": "2026-05-20T10:01:00+00:00",
                "duration_seconds": 60,
                "termination_reason": "twilio_stop",
                "last_error": None,
                "metadata": {
                    "direction": "inbound",
                    "counterparty_label": "***6666",
                },
                "analytics": {
                    "direction": "inbound",
                    "direction_label": "Saapuva",
                    "counterparty_label": "***6666",
                    "topics": [],
                    "topic_labels": [],
                    "follow_up_needed": False,
                    "has_error": False,
                    "resolution_status": "resolved",
                    "resolution_label": "Ratkaistu",
                    "summary_preview": "",
                    "caller_intent": "",
                    "outcome": "",
                    "transcript_turn_count": 0,
                },
                "transcript_turn_count": 0,
            },
        )

        payload = self.service.build_dashboard_payload(
            now=self._dt("2026-05-20T12:00:00+03:00"),
        )

        self.assertFalse(payload["recent_calls"][0]["reservation_created"])

    def test_build_dashboard_payload_supports_legacy_session_logs(self):
        self._write_session(
            "session_legacy.json",
            {
                "call_sid": "CA3",
                "stream_sid": "MZ3",
                "status": "completed",
                "created_at": "2026-05-20T07:00:00+00:00",
                "started_at": "2026-05-20T07:00:00+00:00",
                "ended_at": "2026-05-20T07:02:00+00:00",
                "duration_seconds": 120,
                "termination_reason": "twilio_stop",
                "last_error": None,
                "metadata": {
                    "direction": "inbound",
                    "from_number": "+358401234567",
                },
                "transcript_entries": [
                    {"speaker": "user", "text": "Onko teillä vapaita huoneita viikonlopuksi?"},
                    {"speaker": "assistant", "text": "Tarkistan saatavuuden."},
                ],
            },
        )

        payload = self.service.build_dashboard_payload(
            now=self._dt("2026-05-20T12:00:00+03:00"),
        )

        self.assertEqual(payload["summary"]["total_calls"], 1)
        self.assertEqual(payload["summary"]["resolved_calls"], 1)
        self.assertEqual(payload["recent_calls"][0]["counterparty"], "+358401234567")
        self.assertIn("Saatavuus", payload["recent_calls"][0]["topic_labels"])
        self.assertEqual(payload["recent_calls"][0]["transcript_turn_count"], 2)

    def _write_session(self, filename: str, payload: dict) -> None:
        (self.log_dir / filename).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _dt(raw_value: str):
        from datetime import datetime

        return datetime.fromisoformat(raw_value)


if __name__ == "__main__":
    unittest.main()
