import unittest

from app.models.call import CallSession
from app.services.callback_request_sms import CallbackRequestSmsService


class FakeMessagesClient:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return type("Message", (), {"sid": "SM456"})()


class FakeTwilioClient:
    def __init__(self):
        self.messages = FakeMessagesClient()


class CallbackRequestSmsTests(unittest.TestCase):
    def setUp(self):
        self.twilio_client = FakeTwilioClient()

    def test_send_callback_request_notifies_owner_with_caller_phone_and_reason(self):
        service = CallbackRequestSmsService(
            from_phone="+14780000000",
            owner_phone="+358409998877",
            twilio_client=self.twilio_client,
        )
        session = CallSession(
            metadata={
                "direction": "inbound",
                "from_number": "+358401112233",
            }
        )

        result = service.send_callback_request(
            session=session,
            caller_name="Matti Meikalainen",
            reason="Needs help with a group booking",
        )

        self.assertTrue(result.sent)
        self.assertEqual(result.caller_phone, "+358401112233")
        self.assertEqual(result.owner_phone, "+358409998877")
        self.assertEqual(result.message_sid, "SM456")
        self.assertEqual(len(self.twilio_client.messages.calls), 1)
        sms_body = self.twilio_client.messages.calls[0]["body"]
        self.assertIn("+358401112233", sms_body)
        self.assertIn("Matti Meikalainen", sms_body)
        self.assertIn("group booking", sms_body)
        self.assertIn("Soittajan numero", sms_body)
        self.assertIn("Syy:", sms_body)

    def test_send_callback_request_requires_owner_phone(self):
        service = CallbackRequestSmsService(
            from_phone="+14780000000",
            owner_phone=None,
            twilio_client=self.twilio_client,
        )
        session = CallSession(
            metadata={
                "direction": "inbound",
                "from_number": "+358401112233",
            }
        )

        result = service.send_callback_request(
            session=session,
            caller_name=None,
            reason="Please call back",
        )

        self.assertFalse(result.sent)
        self.assertEqual(result.skipped_reason, "owner_phone_not_configured")
        self.assertEqual(len(self.twilio_client.messages.calls), 0)

    def test_send_callback_request_only_once_per_session(self):
        service = CallbackRequestSmsService(
            from_phone="+14780000000",
            owner_phone="+358409998877",
            twilio_client=self.twilio_client,
        )
        session = CallSession(
            metadata={
                "direction": "inbound",
                "from_number": "+358401112233",
            }
        )

        first = service.send_callback_request(
            session=session,
            caller_name=None,
            reason="Please call back",
        )
        second = service.send_callback_request(
            session=session,
            caller_name=None,
            reason="Please call back again",
        )

        self.assertTrue(first.sent)
        self.assertFalse(second.sent)
        self.assertEqual(second.skipped_reason, "already_sent_for_session")
        self.assertEqual(len(self.twilio_client.messages.calls), 1)


if __name__ == "__main__":
    unittest.main()
