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
# The captured-name group consumes the first token plus up to two further
# space-separated capitalized tokens, so a full first+last name (or a middle name) is
# captured as a single group and replaced by one placeholder instead of leaking every
# token after the first (CR-01: "Nimeni on Matti Virtanen" must redact both "Matti" and
# "Virtanen", not just "Matti").
#
# CR-02 (accepted trade-off, not a defect): name detection here is capitalization-based
# by design. A name that the ASR transcript renders in lowercase (e.g. "olen matti")
# will NOT match this pattern and will pass through unredacted. This is a deliberate,
# known residual risk rather than an oversight: matching the word after "nimeni on"/
# "olen" case-insensitively was tried and rejected, because it caused unacceptable
# over-redaction of ordinary lowercase Finnish words in the same sentence position
# (e.g. "olen kiinnostunut", "olen valmis maksamaan", "olen samaa mielta" would all have
# had their next word wrongly replaced by the name placeholder). Revisiting this
# trade-off requires a design-level mitigation (e.g. a stoplist of common Finnish words,
# or a second lower-confidence pattern), not a simple regex tweak — see CR-02 in
# 03-REVIEW.md for the full analysis.
SELF_ID_PATTERN = re.compile(
    r"\b((?i:nimeni on|olen))\s+"
    r"([A-ZÄÖÅ][\wäöåÄÖÅ'-]{1,30}(?:\s+[A-ZÄÖÅ][\wäöåÄÖÅ'-]{1,30}){0,2})\b"
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
