import json
import logging
from typing import Any, Dict, Optional

from app.models.call import CallSession
from app.services.availability_checker import (
    AvailabilityValidationError,
    availability_checker,
)
from app.services.booking_link_sms import booking_link_sms_service
from app.services.callback_request_sms import callback_request_sms_service
from app.services.realtime_session import (
    AVAILABILITY_TOOL_NAME,
    BOOKING_LINK_SMS_TOOL_NAME,
    CALLBACK_REQUEST_SMS_TOOL_NAME,
    CREATE_RESERVATION_TOOL_NAME,
)
from app.services.reservation_provider import ReservationValidationError, reservation_provider

logger = logging.getLogger(__name__)


async def execute_realtime_tool(
    name: str,
    arguments_json: Optional[str],
    *,
    session: Optional[CallSession] = None,
) -> Dict[str, Any]:
    try:
        arguments = json.loads(arguments_json or "{}")
    except json.JSONDecodeError:
        return {
            "status": "unknown",
            "booking_not_confirmed": True,
            "error_code": "invalid_tool_arguments_json",
            "message_for_assistant": "Tool arguments were not valid JSON.",
        }

    if name == AVAILABILITY_TOOL_NAME:
        try:
            result = await availability_checker.check(arguments)
            return result.to_dict()
        except AvailabilityValidationError as exc:
            return {
                "status": "unknown",
                "booking_not_confirmed": True,
                "error_code": "invalid_availability_query",
                "message_for_assistant": str(exc),
            }
        except Exception as exc:
            logger.exception("Realtime tool execution failed tool=%s error=%s", name, exc)
            return {
                "status": "unknown",
                "booking_not_confirmed": True,
                "error_code": "availability_tool_failed",
                "message_for_assistant": "Availability could not be checked reliably.",
            }

    if name == CREATE_RESERVATION_TOOL_NAME:
        try:
            result = await reservation_provider.create_reservation(arguments, session=session)
            return result.to_dict()
        except ReservationValidationError as exc:
            return {
                "status": "invalid_request",
                "booking_not_confirmed": True,
                "error_code": "invalid_reservation_request",
                "message_for_assistant": str(exc),
            }
        except Exception as exc:
            logger.exception("Realtime tool execution failed tool=%s error=%s", name, exc)
            return {
                "status": "unknown",
                "booking_not_confirmed": True,
                "error_code": "create_reservation_failed",
                "message_for_assistant": "Varausta ei pystytty tekemään luotettavasti juuri nyt.",
            }

    if name == BOOKING_LINK_SMS_TOOL_NAME:
        try:
            result = booking_link_sms_service.send_calendar_link(
                session=session,
                tuote_id=_read_optional_str(arguments.get("tuoteId")),
                unit_id=_read_optional_str(arguments.get("unitId")),
            )
            return result.to_dict()
        except Exception as exc:
            logger.exception("Realtime tool execution failed tool=%s error=%s", name, exc)
            return {
                "status": "not_sent",
                "sent": False,
                "booking_not_confirmed": True,
                "error_code": "booking_link_sms_failed",
                "message_for_assistant": "Tekstiviestin lahettaminen ei onnistunut luotettavasti.",
            }

    if name == CALLBACK_REQUEST_SMS_TOOL_NAME:
        try:
            result = callback_request_sms_service.send_callback_request(
                session=session,
                caller_name=_read_optional_str(arguments.get("callerName")),
                reason=_read_optional_str(arguments.get("reason")),
            )
            return result.to_dict()
        except Exception as exc:
            logger.exception("Realtime tool execution failed tool=%s error=%s", name, exc)
            return {
                "status": "not_sent",
                "sent": False,
                "booking_not_confirmed": True,
                "error_code": "callback_request_sms_failed",
                "message_for_assistant": "Yhteydenottopyynnon lahettaminen ei onnistunut luotettavasti.",
            }

    return {
        "status": "unknown",
        "booking_not_confirmed": True,
        "error_code": "unknown_tool",
        "message_for_assistant": f"Unknown tool: {name}",
    }


def _read_optional_str(value: Any) -> Optional[str]:
    cleaned = str(value or "").strip()
    return cleaned or None
