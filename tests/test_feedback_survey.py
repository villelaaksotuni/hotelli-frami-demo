import json
import shutil
import unittest
from pathlib import Path

from app.services.feedback_survey import FeedbackSurveyService


class FakeMessagesClient:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return type("Message", (), {"sid": "SM999"})()


class FakeTwilioClient:
    def __init__(self):
        self.messages = FakeMessagesClient()


class FeedbackSurveyTests(unittest.TestCase):
    def setUp(self):
        self.temp_root = Path("tests") / ".tmp_feedback_survey" / self._testMethodName
        shutil.rmtree(self.temp_root, ignore_errors=True)
        self.temp_root.mkdir(parents=True, exist_ok=True)
        self.history_path = self.temp_root / "history.json"
        self.twilio_client = FakeTwilioClient()
        self.service = FeedbackSurveyService(
            history_path=self.history_path,
            enabled=True,
            survey_message="Rate us 1-10",
            from_phone="+14780000000",
            twilio_client=self.twilio_client,
        )

    def tearDown(self):
        shutil.rmtree(self.temp_root, ignore_errors=True)

    def test_send_invite_only_once_per_unique_phone(self):
        metadata = {"direction": "outbound", "to_number": "+358401112233"}
        dialogue_turns = [{"speaker": "user", "text": "Need a room."}]

        first = self.service.send_invite_if_needed(
            metadata=metadata,
            call_sid="CA1",
            stream_sid="MZ1",
            language="en",
            dialogue_turns=dialogue_turns,
        )
        second = self.service.send_invite_if_needed(
            metadata=metadata,
            call_sid="CA2",
            stream_sid="MZ2",
            language="en",
            dialogue_turns=dialogue_turns,
        )

        self.assertTrue(first.sent)
        self.assertEqual(first.message_sid, "SM999")
        self.assertFalse(second.sent)
        self.assertEqual(second.skipped_reason, "already_invited")
        self.assertEqual(len(self.twilio_client.messages.calls), 1)
        self.assertIn("free-form feedback", self.twilio_client.messages.calls[0]["body"])

    def test_record_response_accepts_rating_and_persists_it(self):
        metadata = {"direction": "outbound", "to_number": "+358401112233"}
        self.service.send_invite_if_needed(
            metadata=metadata,
            call_sid="CA1",
            stream_sid="MZ1",
            language="fi",
            dialogue_turns=[{"speaker": "user", "text": "Need a room."}],
        )

        result = self.service.record_response(
            from_phone="+358401112233",
            body="8",
            message_sid="SMREPLY1",
        )

        self.assertTrue(result.accepted)
        self.assertEqual(result.rating, 8)
        history = json.loads(self.history_path.read_text(encoding="utf-8"))
        self.assertEqual(history["responses"][0]["rating"], 8)

    def test_record_response_accepts_freeform_feedback(self):
        metadata = {"direction": "outbound", "to_number": "+358401112233"}
        self.service.send_invite_if_needed(
            metadata=metadata,
            call_sid="CA1",
            stream_sid="MZ1",
            language="fi",
            dialogue_turns=[{"speaker": "user", "text": "Need a room."}],
        )

        result = self.service.record_response(
            from_phone="+358401112233",
            body="great service",
            message_sid="SMREPLY2",
        )

        self.assertTrue(result.accepted)
        self.assertIsNone(result.rating)
        history = json.loads(self.history_path.read_text(encoding="utf-8"))
        self.assertEqual(history["responses"][0]["freeform_feedback"], "great service")


if __name__ == "__main__":
    unittest.main()
