from __future__ import annotations

import re

# Requires a `+` country-code prefix or a domestic trunk-zero prefix, so an ISO date, a
# hyphenated confirmation number and a house number no longer match at all. Every
# quantifier is bounded on a single non-nested character class, keeping matching linear.
PHONE_PATTERN = re.compile(
    r"(?<!\w)(?:\+358[\d\s\-()]{6,14}|\+\d{1,3}[\d\s\-()]{6,16}|0\d[\d\s\-()]{5,13})(?!\w)"
)
# Raised from 5+ to 7+ bare digits: a five-digit postal code, a five-digit total price and
# a four-digit year now fall below the threshold and survive, while a prefix-less long
# digit run (a dropped leading zero, a country code dictated without its plus) is still
# caught as defence in depth.
LONG_NUMBER_PATTERN = re.compile(r"\b\d{7,}\b")
# Inline-scoped flag: the introducing phrase alternation is case-insensitive, but the
# name's `[A-ZÄÖÅ]` first-character class stays case-sensitive, so the capitalisation
# requirement on the captured name is not defeated by a module-level IGNORECASE flag.
SELF_ID_PATTERN = re.compile(
    r"\b((?i:nimeni on|olen))\s+([A-ZÄÖÅ][\wäöåÄÖÅ'-]{1,30})\b"
)

PHONE_PLACEHOLDER = "[puhelin]"
NAME_PLACEHOLDER = "[nimi]"

# Lower bound only, enforced in code rather than in the pattern: a character-class length
# bound on a mixed digits/space/hyphen/paren run counts separators, not digits, so the
# actual digit count is counted here after the pattern has selected a candidate. No upper
# bound is enforced — a 16+ digit run with a `+`/`0` prefix is a card number or a
# concatenated pair of phone numbers, not a date or a price, and redacting it keeps the
# failure on the privacy-safe side.
MIN_PHONE_DIGITS = 7


def _replace_self_id(match: re.Match[str]) -> str:
    return f"{match.group(1)} {NAME_PLACEHOLDER}"


def _replace_phone(match: re.Match[str]) -> str:
    digit_count = sum(1 for char in match.group(0) if char.isdigit())
    if digit_count < MIN_PHONE_DIGITS:
        return match.group(0)
    return PHONE_PLACEHOLDER


def redact_for_broadcast(text: str) -> str:
    if not text:
        return text

    redacted = PHONE_PATTERN.sub(_replace_phone, text)
    redacted = LONG_NUMBER_PATTERN.sub(PHONE_PLACEHOLDER, redacted)
    redacted = SELF_ID_PATTERN.sub(_replace_self_id, redacted)
    return redacted
