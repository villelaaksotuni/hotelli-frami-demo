from __future__ import annotations

import re

PHONE_PATTERN = re.compile(r"(?<!\w)(?:\+?\d[\d\s\-()]{5,}\d)")
LONG_NUMBER_PATTERN = re.compile(r"\b\d{5,}\b")
# Inline-scoped flag: the introducing phrase alternation is case-insensitive, but the
# name's `[A-ZÄÖÅ]` first-character class stays case-sensitive, so the capitalisation
# requirement on the captured name is not defeated by a module-level IGNORECASE flag.
SELF_ID_PATTERN = re.compile(
    r"\b((?i:nimeni on|olen))\s+([A-ZÄÖÅ][\wäöåÄÖÅ'-]{1,30})\b"
)

PHONE_PLACEHOLDER = "[puhelin]"
NAME_PLACEHOLDER = "[nimi]"


def _replace_self_id(match: re.Match[str]) -> str:
    return f"{match.group(1)} {NAME_PLACEHOLDER}"


def redact_for_broadcast(text: str) -> str:
    if not text:
        return text

    redacted = PHONE_PATTERN.sub(PHONE_PLACEHOLDER, text)
    redacted = LONG_NUMBER_PATTERN.sub(PHONE_PLACEHOLDER, redacted)
    redacted = SELF_ID_PATTERN.sub(_replace_self_id, redacted)
    return redacted
