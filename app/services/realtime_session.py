import asyncio
import json
import logging
from typing import Any

from app.config.settings import settings
from app.models.call import CallConfig

logger = logging.getLogger(__name__)

SESSION_UPDATE_TIMEOUT_SECONDS = 5
AVAILABILITY_TOOL_NAME = "check_availability"
CALLBACK_REQUEST_SMS_TOOL_NAME = "send_owner_callback_request_sms"
CREATE_RESERVATION_TOOL_NAME = "create_reservation"
AVAILABILITY_TOOL_SCHEMA = {
    "type": "function",
    "name": AVAILABILITY_TOOL_NAME,
    "description": (
        "Return current availability and prices from the Hotelli Frami demonstration "
        "reservation store for a requested stay. This tool does not itself create a "
        "reservation."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "arrivalDate": {
                "type": "string",
                "description": "Arrival date in YYYY-MM-DD format.",
            },
            "nights": {
                "type": "integer",
                "minimum": 1,
                "description": "Number of nights requested.",
            },
            "guests": {
                "type": "integer",
                "minimum": 1,
                "description": "Number of guests.",
            },
            "area": {
                "type": "string",
                "enum": ["Framinranta", "Kampusaukio", "Jokipuisto", "any"],
                "description": "Optional preferred area. Use any when there is no area preference.",
            },
            "unitName": {
                "type": "string",
                "description": (
                    "Optional apartment or property name mentioned by the caller, such as "
                    "'Huoneistohotelli Framinranta', 'Jokipuistopark asunto 2', or 'Kampusaukio 7 asunto 5'."
                ),
            },
            "unitId": {
                "type": "string",
                "description": (
                    "Optional internal unit id. Prefer unitName when the caller refers "
                    "to an apartment or property by name."
                ),
            },
        },
        "required": ["arrivalDate", "nights", "guests"],
    },
}
CREATE_RESERVATION_TOOL_SCHEMA = {
    "type": "function",
    "name": CREATE_RESERVATION_TOOL_NAME,
    "description": (
        "Create a reservation in the Hotelli Frami demonstration reservation store. "
        "The reservation is a demo record only and is never a real, binding hotel booking."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "arrivalDate": {
                "type": "string",
                "description": "Arrival date in YYYY-MM-DD format.",
            },
            "nights": {
                "type": "integer",
                "minimum": 1,
                "description": "Number of nights requested.",
            },
            "guests": {
                "type": "integer",
                "minimum": 1,
                "description": "Number of guests.",
            },
            "unitId": {
                "type": "string",
                "description": (
                    "The exact unit_id returned by the availability tool for the unit "
                    "the caller wants to reserve."
                ),
            },
            "unitName": {
                "type": "string",
                "description": (
                    "The apartment or property name as the caller said it. Use only "
                    "when no unitId is available."
                ),
            },
        },
        "required": ["arrivalDate", "nights", "guests", "unitId"],
    },
}
CALLBACK_REQUEST_SMS_TOOL_SCHEMA = {
    "type": "function",
    "name": CALLBACK_REQUEST_SMS_TOOL_NAME,
    "description": (
        "Send the Hotelli Frami reception an SMS callback request or an urgent/critical "
        "situation alert."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "callerName": {
                "type": "string",
                "description": "Optional caller name if the caller gives it.",
            },
            "reason": {
                "type": "string",
                "description": (
                    "Short Finnish summary for the reception, such as booking help, invoice "
                    "question, access problem, urgent issue, or special arrangement."
                ),
            },
        },
    },
}


def _build_tool_schemas() -> list[dict[str, Any]]:
    tools = [AVAILABILITY_TOOL_SCHEMA, CREATE_RESERVATION_TOOL_SCHEMA]
    if settings.callback_request_to_phone:
        tools.append(CALLBACK_REQUEST_SMS_TOOL_SCHEMA)
    return tools


async def initialize_session(openai_ws: Any, config: CallConfig) -> None:
    session_update = _build_session_update_payload(config, instructions=config.system_message)
    await asyncio.wait_for(
        openai_ws.send(json.dumps(session_update)),
        timeout=SESSION_UPDATE_TIMEOUT_SECONDS,
    )
    session_payload = session_update["session"]
    voice = session_payload.get("voice")
    if voice is None:
        voice = session_payload["audio"]["output"]["voice"]
    payload_temperature = session_payload.get("temperature")
    logger.info(
        "Session configured: model=%s voice=%s language=%s sent_temperature=%s reasoning_effort=%s",
        session_payload["model"],
        voice,
        config.language,
        payload_temperature,
        config.reasoning_effort,
    )


async def request_initial_assistant_response(openai_ws: Any, config: CallConfig) -> None:
    response_create = _build_initial_response_create_payload(config)
    await asyncio.wait_for(
        openai_ws.send(json.dumps(response_create)),
        timeout=SESSION_UPDATE_TIMEOUT_SECONDS,
    )
    logger.info("Requested initial assistant response language=%s", config.language)


async def update_session_instructions(
    openai_ws: Any,
    config: CallConfig,
    instructions: str,
) -> None:
    session_update = _build_session_update_payload(config, instructions=instructions)
    await asyncio.wait_for(
        openai_ws.send(json.dumps(session_update)),
        timeout=SESSION_UPDATE_TIMEOUT_SECONDS,
    )


def _build_session_update_payload(config: CallConfig, instructions: str) -> dict:
    supported_voices = {
        "alloy",
        "ash",
        "ballad",
        "coral",
        "echo",
        "sage",
        "shimmer",
        "verse",
    }

    voice = config.voice if config.voice in supported_voices else settings.default_voice
    session = {
        "type": "session.update",
        "session": {
            "type": "realtime",
            "model": settings.openai_realtime_model,
            "audio": {
                "input": {
                    "format": {"type": "audio/pcmu"},
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.75,
                        "silence_duration_ms": 1200,
                        "create_response": True,
                        "interrupt_response": True,
                    },
                    "transcription": {
                        "model": "whisper-1",
                        "language": config.language,
                        "prompt": settings.default_transcription_prompt,
                    },
                },
                "output": {
                    "format": {"type": "audio/pcmu"},
                    "voice": voice,
                },
            },
            "instructions": instructions,
            "output_modalities": ["audio"],
            "tools": _build_tool_schemas(),
            "tool_choice": "auto",
        },
    }

    if _supports_temperature(settings.openai_realtime_model):
        session["session"]["temperature"] = config.temperature

    # Current OpenAI Realtime models share the same nested audio session shape.
    # Only the gpt-realtime-2 family gets an explicit reasoning configuration block.
    if _supports_reasoning_effort(settings.openai_realtime_model):
        session["session"]["reasoning"] = {"effort": config.reasoning_effort}

    return session


def _build_initial_response_create_payload(config: CallConfig) -> dict:
    return {
        "type": "response.create",
        "response": {
            "instructions": config.opening_message,
            "output_modalities": ["audio"],
        },
    }


def _supports_reasoning_effort(model: str) -> bool:
    return model.startswith("gpt-realtime-2")


def _supports_temperature(model: str) -> bool:
    return not model.startswith("gpt-realtime")
