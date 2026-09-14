import asyncio
import json
import unittest
from unittest.mock import patch

from app.models.call import CallSession
from app.services.callback_request_sms import CallbackRequestSmsService
from app.services.realtime_session import CALLBACK_REQUEST_SMS_TOOL_NAME
from app.services.realtime_tools import execute_realtime_tool


class FakeMessagesClient:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return type("Message", (), {"sid": "SM789"})()


class FakeTwilioClient:
    def __init__(self):
        self.messages = FakeMessagesClient()


class ToolDispatchDestinationInjectionTests(unittest.TestCase):
    """SAFE-04: an injected destination never leaves the building.

    Proves the full path — model-supplied tool arguments, through
    execute_realtime_tool, through CallbackRequestSmsService.send_callback_request,
    to the single Twilio messages.create call — cannot be steered to an
    attacker-chosen destination.
    """

    def test_injected_destination_keys_never_reach_the_twilio_send(self):
        twilio_client = FakeTwilioClient()
        owner_phone = "+358409998877"
        service = CallbackRequestSmsService(
            from_phone="+14780000000",
            owner_phone=owner_phone,
            twilio_client=twilio_client,
        )
        session = CallSession(
            metadata={
                "direction": "inbound",
                "from_number": "+358401112233",
            }
        )

        injected_numbers = {
            "phone": "+15550000001",
            "to": "+15550000002",
            "destination": "+15550000003",
            "recipient": "+15550000004",
            "owner_phone": "+15550000005",
            "toNumber": "+15550000006",
        }
        arguments = {
            "callerName": "Matti Meikalainen",
            "reason": "Needs help with a group booking",
            **injected_numbers,
        }

        with patch(
            "app.services.realtime_tools.callback_request_sms_service", service
        ):
            result = asyncio.run(
                execute_realtime_tool(
                    CALLBACK_REQUEST_SMS_TOOL_NAME,
                    json.dumps(arguments),
                    session=session,
                )
            )

        self.assertTrue(result.get("sent"))
        self.assertEqual(len(twilio_client.messages.calls), 1)
        recorded_call = twilio_client.messages.calls[0]
        self.assertEqual(recorded_call["to"], owner_phone)

        serialized_kwargs = " ".join(str(value) for value in recorded_call.values())
        for injected_number in injected_numbers.values():
            self.assertNotIn(injected_number, serialized_kwargs)


if __name__ == "__main__":
    unittest.main()
