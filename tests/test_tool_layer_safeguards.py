import asyncio
import dataclasses
import json
import unittest
from unittest.mock import patch

from app.config.settings import settings
from app.models.call import CallConfig, CallSession
from app.services.callback_request_sms import CallbackRequestSmsService
from app.services.live_broadcast import LIVE_SLOT_KEYS
from app.services.realtime_session import (
    AVAILABILITY_TOOL_NAME,
    CALLBACK_REQUEST_SMS_TOOL_NAME,
    CREATE_RESERVATION_TOOL_NAME,
    _build_session_update_payload,
)
from app.services.realtime_tools import execute_realtime_tool

# Substring rule (SAFE-04, Task 2): a schema property key or LIVE_SLOT_KEYS entry
# is "destination-shaped" if, lowercased and stripped of underscores, it equals
# "to" or contains any of these substrings.
DESTINATION_SUBSTRINGS = ("phone", "destination", "recipient", "msisdn", "sendto")


def _is_destination_shaped(key: str) -> bool:
    flat = key.lower().replace("_", "")
    return flat == "to" or any(substring in flat for substring in DESTINATION_SUBSTRINGS)


class FakeReservationProvider:
    def __init__(self):
        self.check_availability_calls = []
        self.create_reservation_calls = []

    async def check_availability(self, payload):
        self.check_availability_calls.append(payload)
        return _FakeAvailabilityResult()

    async def create_reservation(self, payload, *, session=None):
        self.create_reservation_calls.append(payload)
        return _FakeCreateReservationResult()


class _FakeAvailabilityResult:
    def to_dict(self):
        return {
            "status": "available",
            "booking_not_confirmed": True,
            "message_for_assistant": "fake availability result",
        }


class _FakeCreateReservationResult:
    status = "invalid_request"
    reservation = None

    def to_dict(self):
        return {
            "status": self.status,
            "reservation": None,
            "message_for_assistant": "fake create-reservation result",
        }


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


class ToolSchemaShapeRegressionTests(unittest.TestCase):
    """SAFE-04 Task 2: no exposed tool schema declares a destination-shaped parameter.

    Derives the exposed tool list from _build_session_update_payload(...) rather
    than from the schema constants alone, so the assertion covers what the model
    actually receives.
    """

    def test_exposed_tool_list_has_exactly_three_schemas_and_no_destination_key(self):
        settings_with_callback = dataclasses.replace(
            settings, callback_request_to_phone="+358401234567"
        )
        with patch("app.services.realtime_session.settings", settings_with_callback):
            payload = _build_session_update_payload(CallConfig(), instructions="x")
        tools = payload["session"]["tools"]
        self.assertEqual(len(tools), 3, tools)

        offenders = []
        for tool in tools:
            properties = (tool.get("parameters") or {}).get("properties", {})
            for key in properties:
                if _is_destination_shaped(key):
                    offenders.append((tool.get("name"), key))
        self.assertEqual(
            offenders,
            [],
            f"destination-shaped parameter(s) found in exposed tool schema(s): {offenders}",
        )

    def test_callback_tool_omitted_when_owner_phone_not_configured(self):
        settings_without_callback = dataclasses.replace(
            settings, callback_request_to_phone=None
        )
        with patch("app.services.realtime_session.settings", settings_without_callback):
            payload = _build_session_update_payload(CallConfig(), instructions="x")
        tools = payload["session"]["tools"]
        tool_names = [tool.get("name") for tool in tools]
        self.assertEqual(len(tools), 2, tools)
        self.assertNotIn(CALLBACK_REQUEST_SMS_TOOL_NAME, tool_names)

    def test_live_slot_keys_contain_no_destination_shaped_key(self):
        offenders = [key for key in LIVE_SLOT_KEYS if _is_destination_shaped(key)]
        self.assertEqual(
            offenders,
            [],
            f"destination-shaped key(s) found in LIVE_SLOT_KEYS: {offenders}",
        )


class UnexpectedArgumentDispatchTests(unittest.TestCase):
    """SAFE-04 Task 2: unexpected argument keys are inert across every dispatch branch."""

    def test_availability_dispatch_ignores_unexpected_keys(self):
        fake_provider = FakeReservationProvider()
        arguments = {
            "arrivalDate": "2026-10-01",
            "nights": 2,
            "guests": 2,
            "phone": "+15550000009",
            "unexpectedKey": "irrelevant",
        }

        with patch("app.services.realtime_tools.reservation_provider", fake_provider):
            result = asyncio.run(
                execute_realtime_tool(AVAILABILITY_TOOL_NAME, json.dumps(arguments))
            )

        self.assertIsInstance(result, dict)
        self.assertEqual(len(fake_provider.check_availability_calls), 1)
        self.assertEqual(fake_provider.check_availability_calls[0], arguments)

    def test_create_reservation_dispatch_ignores_unexpected_keys(self):
        fake_provider = FakeReservationProvider()
        session = CallSession(
            metadata={"direction": "inbound", "from_number": "+358401112233"}
        )
        arguments = {
            "arrivalDate": "2026-10-01",
            "nights": 2,
            "guests": 2,
            "unitId": "unit-1",
            "phone": "+15550000009",
            "unexpectedKey": "irrelevant",
        }

        with patch("app.services.realtime_tools.reservation_provider", fake_provider):
            result = asyncio.run(
                execute_realtime_tool(
                    CREATE_RESERVATION_TOOL_NAME,
                    json.dumps(arguments),
                    session=session,
                )
            )

        self.assertIsInstance(result, dict)
        self.assertEqual(len(fake_provider.create_reservation_calls), 1)
        self.assertEqual(fake_provider.create_reservation_calls[0], arguments)

    def test_callback_request_sms_dispatch_ignores_unexpected_keys(self):
        twilio_client = FakeTwilioClient()
        owner_phone = "+358409998877"
        service = CallbackRequestSmsService(
            from_phone="+14780000000",
            owner_phone=owner_phone,
            twilio_client=twilio_client,
        )
        session = CallSession(
            metadata={"direction": "inbound", "from_number": "+358401112244"}
        )
        arguments = {
            "callerName": "Kalle",
            "reason": "Kysymys varauksesta",
            "phone": "+15550000009",
            "unexpectedKey": "irrelevant",
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

        self.assertIsInstance(result, dict)
        self.assertEqual(len(twilio_client.messages.calls), 1)

    def test_unknown_tool_returns_unknown_tool_error_and_makes_no_collaborator_call(self):
        fake_provider = FakeReservationProvider()
        twilio_client = FakeTwilioClient()
        service = CallbackRequestSmsService(
            from_phone="+14780000000",
            owner_phone="+358409998877",
            twilio_client=twilio_client,
        )

        with patch(
            "app.services.realtime_tools.reservation_provider", fake_provider
        ), patch("app.services.realtime_tools.callback_request_sms_service", service):
            result = asyncio.run(
                execute_realtime_tool(
                    "some_unrecognized_tool_name",
                    json.dumps({"phone": "+15550000009"}),
                )
            )

        self.assertEqual(result.get("error_code"), "unknown_tool")
        self.assertEqual(len(fake_provider.check_availability_calls), 0)
        self.assertEqual(len(fake_provider.create_reservation_calls), 0)
        self.assertEqual(len(twilio_client.messages.calls), 0)


if __name__ == "__main__":
    unittest.main()
