from typing import Any, Dict

from app.config.settings import settings
from app.models.call import CallConfig
from app.services.prompt_store import prompt_store


def build_default_call_config() -> CallConfig:
    snapshot = prompt_store.get_snapshot()
    return CallConfig(
        system_message=snapshot.active_prompt,
        opening_message=snapshot.active_opening_message,
        voice=settings.default_voice,
        language=settings.default_language,
        temperature=settings.default_temperature,
        reasoning_effort=settings.default_reasoning_effort,
        metadata={},
    )


async def build_call_config_from_payload(body: Dict[str, Any]) -> CallConfig:
    """
    Translate your frontend/backend payload into a runtime call config.

    The pilot runtime currently uses the active prompt store entry as-is.
    """
    snapshot = prompt_store.get_snapshot()
    system_message = body.get("system_message") or snapshot.active_prompt
    opening_message = body.get("opening_message") or snapshot.active_opening_message

    return CallConfig(
        system_message=system_message,
        opening_message=opening_message,
        voice=body.get("voice") or settings.default_voice,
        language=body.get("language") or settings.default_language,
        temperature=float(body.get("temperature", settings.default_temperature)),
        reasoning_effort=body.get("reasoning_effort") or settings.default_reasoning_effort,
        metadata=body.get("metadata") or {},
    )
