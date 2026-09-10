import unittest

from app.models.call import CallSession
from app.services.booking_link_sms import BookingLinkSmsService


class FakeMessagesClient:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return type("Message", (), {"sid": "SM123"})()


class FakeTwilioClient:
    def __init__(self):
        self.messages = FakeMessagesClient()


class BookingLinkSmsTests(unittest.TestCase):
    def setUp(self):
        self.twilio_client = FakeTwilioClient()
        self.service = BookingLinkSmsService(
            from_phone="+14780000000",
            twilio_client=self.twilio_client,
        )

    def test_send_calendar_link_uses_inbound_caller_number_and_tuote_id(self):
        session = CallSession(
            metadata={
                "direction": "inbound",
                "from_number": "+358401112233",
            }
        )

        result = self.service.send_calendar_link(
            session=session,
            tuote_id="9202-51004",
            unit_id=None,
        )

        self.assertTrue(result.sent)
        self.assertEqual(result.to_phone, "+358401112233")
        self.assertEqual(result.unit_id, "jokipuistopark-asunto-2")
        self.assertEqual(result.message_sid, "SM123")
        self.assertEqual(len(self.twilio_client.messages.calls), 1)
        self.assertIn("Jokipuistopark asunto 2", self.twilio_client.messages.calls[0]["body"])
        self.assertIn("Tässä varauskalenteri", self.twilio_client.messages.calls[0]["body"])

    def test_send_calendar_link_uses_conversation_language_for_english_sms(self):
        session = CallSession(
            metadata={
                "direction": "inbound",
                "from_number": "+358401112233",
            }
        )
        session.append_transcript("user", "Hi, I need a room for tomorrow")
        session.append_transcript("assistant", "I can send you the booking calendar by SMS.")

        result = self.service.send_calendar_link(
            session=session,
            tuote_id="9202-51004",
            unit_id=None,
        )

        self.assertTrue(result.sent)
        self.assertIn(
            "Here is the booking calendar",
            self.twilio_client.messages.calls[0]["body"],
        )

    def test_send_calendar_link_skips_duplicate_unit_in_same_session(self):
        session = CallSession(
            metadata={
                "direction": "inbound",
                "from_number": "+358401112233",
            }
        )

        first = self.service.send_calendar_link(
            session=session,
            tuote_id="9202-51004",
            unit_id=None,
        )
        second = self.service.send_calendar_link(
            session=session,
            tuote_id="9202-51004",
            unit_id=None,
        )

        self.assertTrue(first.sent)
        self.assertFalse(second.sent)
        self.assertEqual(second.skipped_reason, "already_sent_for_unit")
        self.assertEqual(len(self.twilio_client.messages.calls), 1)

    def test_send_calendar_link_requires_caller_phone(self):
        session = CallSession(metadata={"direction": "inbound"})

        result = self.service.send_calendar_link(
            session=session,
            tuote_id="9202-51004",
            unit_id=None,
        )

        self.assertFalse(result.sent)
        self.assertEqual(result.skipped_reason, "missing_phone")
        self.assertEqual(len(self.twilio_client.messages.calls), 0)

    def test_send_calendar_link_prefers_live_call_origin_number(self):
        session = CallSession(
            metadata={
                "direction": "outbound",
                "from_number": "+358401112233",
                "to_number": "+358409998877",
            }
        )

        result = self.service.send_calendar_link(
            session=session,
            tuote_id="9202-51004",
            unit_id=None,
        )

        self.assertTrue(result.sent)
        self.assertEqual(result.to_phone, "+358401112233")
        self.assertEqual(self.twilio_client.messages.calls[0]["to"], "+358401112233")


if __name__ == "__main__":
    unittest.main()
