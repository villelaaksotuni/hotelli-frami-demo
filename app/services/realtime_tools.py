import json
import logging
from typing import Any, Dict, Optional

from app.models.call import CallSession
from app.services.callback_request_sms import callback_request_sms_service
from app.services.live_broadcast import live_broadcast_hub
from app.services.realtime_session import (
    AVAILABILITY_TOOL_NAME,
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
        live_broadcast_hub.publish_capability(tool=name)
        live_broadcast_hub.publish_agent_state(tool=name, arguments=arguments)
        logger.info("Live agent-state published tool=%s", name)
        try:
            result = await reservation_provider.check_availability(arguments)
            return result.to_dict()
        except ReservationValidationError as exc:
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
        if session is None:
            logger.warning(
                "Refusing create_reservation dispatch tool=%s: no session resolved for call",
                name,
            )
            return {
                "status": "invalid_request",
                "booking_not_confirmed": True,
                "error_code": "session_unavailable",
                "message_for_assistant": "Varausta ei voitu yhdistää puheluun juuri nyt.",
            }
        live_broadcast_hub.publish_capability(tool=name)
        live_broadcast_hub.publish_agent_state(tool=name, arguments=arguments)
        logger.info("Live agent-state published tool=%s", name)
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

    if name == CALLBACK_REQUEST_SMS_TOOL_NAME:
        live_broadcast_hub.publish_capability(tool=name)
        live_broadcast_hub.publish_agent_state(tool=name, arguments=arguments)
        logger.info("Live agent-state published tool=%s", name)
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
