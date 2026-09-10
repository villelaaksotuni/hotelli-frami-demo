from app.config.settings import settings

TWILIO_LANGUAGE_MAP = {
    "fi": "fi-FI",
    "en": "en-US",
}

TWILIO_GREETING_MAP = {
    "fi-FI": "Yhdistan puhelusi nyt.",
    "en-US": "Connecting you now.",
}

TWILIO_AI_DISCLOSURE_MAP = {
    "fi-FI": lambda: settings.twilio_ai_disclosure_message_fi,
    "en-US": lambda: settings.twilio_ai_disclosure_message_en,
}

DEFAULT_TWILIO_LANGUAGE = "en-US"


def get_twilio_language_code(app_language: str | None) -> str:
    if not app_language:
        return DEFAULT_TWILIO_LANGUAGE
    normalized = app_language.strip().lower()
    return TWILIO_LANGUAGE_MAP.get(normalized, DEFAULT_TWILIO_LANGUAGE)


def get_incoming_call_greeting(app_language: str | None = None) -> tuple[str, str]:
    twilio_language = get_twilio_language_code(app_language or settings.default_language)
    if not settings.twilio_preamble_enabled:
        return "", twilio_language

    greeting = TWILIO_GREETING_MAP.get(
        twilio_language,
        TWILIO_GREETING_MAP[DEFAULT_TWILIO_LANGUAGE],
    )
    announcement_parts: list[str] = []

    if settings.twilio_ai_disclosure_enabled:
        disclosure_getter = TWILIO_AI_DISCLOSURE_MAP.get(
            twilio_language,
            TWILIO_AI_DISCLOSURE_MAP[DEFAULT_TWILIO_LANGUAGE],
        )
        disclosure = disclosure_getter().strip()
        if disclosure:
            announcement_parts.append(disclosure)

    announcement_parts.append(greeting)
    return " ".join(announcement_parts), twilio_language
