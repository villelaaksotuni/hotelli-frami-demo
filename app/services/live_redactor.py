from __future__ import annotations

import re

PHONE_PATTERN = re.compile(r"(?<!\w)(?:\+?\d[\d\s\-()]{5,}\d)")
LONG_NUMBER_PATTERN = re.compile(r"\b\d{5,}\b")
SELF_ID_PATTERN = re.compile(
    r"\b(nimeni on|olen)\s+([A-ZÄÖÅ][\wäöåÄÖÅ'-]{1,30})\b",
    re.IGNORECASE,
)

PHONE_PLACEHOLDER = "[puhelin]"
NAME_PLACEHOLDER = "[nimi]"


def redact_for_broadcast(text: str) -> str:
    if not text:
        return text

    redacted = PHONE_PATTERN.sub(PHONE_PLACEHOLDER, text)
    redacted = LONG_NUMBER_PATTERN.sub(PHONE_PLACEHOLDER, redacted)
    redacted = SELF_ID_PATTERN.sub(
        lambda match: f"{match.group(1)} {NAME_PLACEHOLDER}", redacted
    )
    return redacted
