from __future__ import annotations

import re

# CONTENT_POLICY_PLACEHOLDER stands in for an entire withheld utterance, never a
# partial redaction. Replacing only the offending word inside a sentence leaks the
# surrounding structure of a slur or threat (who it was aimed at, what was
# threatened); a single whole-utterance placeholder is far easier to reason about
# and is what apply_content_policy always returns on a match.
CONTENT_POLICY_PLACEHOLDER = "[sisältöä ei näytetä]"

# --- Severity line -------------------------------------------------------------
# Three categories are IN SCOPE for whole-utterance replacement, because each one
# is a targeted harm aimed at a person rather than ordinary spoken register:
#   1. Identity and ethnic slurs
#   2. Sexually explicit terms directed at a person (an insult, not neutral speech)
#   3. Direct threats of violence against a person
#
# CR-03 (accepted trade-off, not a defect — mirrors CR-02 in live_redactor.py):
# common Finnish conversational expletives used as bare interjections ("saatana",
# "perkele", "vittu" said as an exclamation, aimed at nothing) are deliberately OUT
# of scope. Those words function as ordinary spoken-Finnish register — swearing as
# punctuation, not as an attack on anyone — and matching them would blank a large
# fraction of genuine, harmless utterances. That is exactly the over-redaction
# defect Phase 3's 03-05 gap-closure plan had to fix in the PII redactor (see
# live_redactor.py's CR-02 comment for the same lesson learned there): a filter
# that is too eager destroys the demo's core value of watching a real conversation
# unfold. This module draws the severity line at targeted harm, not at register —
# for example "vittu" alone passes through, but "vittupää" aimed at a person (the
# sexual-insult pattern below) does not.
#
# CR-04 (accepted residual risk, per 04-RESEARCH.md Pitfall 5): a static pattern
# list cannot catch creative misspellings, other languages, or context-dependent
# harassment that never says a listed word at all. It is sized to a low-stakes
# public demo's realistic threat model, not to a production moderation product.
# Periodic human review of what actually reaches the public transcript is the
# mitigation for this residual risk, not an ever-growing wordlist.
# ---------------------------------------------------------------------------------

# Identity/ethnic slur stems. Every quantifier below is bounded on a single
# non-nested character class (linear matching, same discipline live_redactor.py's
# comments call out), and the inflection suffix is a small bounded span so ordinary
# Finnish case endings (partitive, genitive, plural) still match without runaway
# backtracking.
SLUR_PATTERN = re.compile(r"\b(neekeri|ryss[aä])\w{0,4}\b", re.IGNORECASE)

# Sexually explicit terms used as a direct insult aimed at a person — gated on an
# address token ("senkin"/"sinä") immediately before the term, so the underlying
# word in neutral or self-referential context is not what this pattern polices.
SEXUAL_INSULT_PATTERN = re.compile(
    r"\b(senkin|sin[aä])\s+(huora|lutka|vittup[aä]{2})\w{0,4}\b",
    re.IGNORECASE,
)

# Direct threats of violence against a person: a threat verb stem followed by a
# second-person or third-person object pronoun.
THREAT_PATTERN = re.compile(
    r"\b(tap(?:an|aisin|oin)|hakkaan|tuhoan|vahingoitan)\s+"
    r"(sinut|sut|teid[aä]t|h[aä]net)\b",
    re.IGNORECASE,
)

# WR-02: the object-pronoun, then verb order ("sinut tapan", "sinut minä
# tapan") is a grammatical fronted-object variant of the exact same threat
# THREAT_PATTERN polices — flexible Finnish word order, not a distinct
# category — so it needs its own pattern rather than an unbounded reorder of
# THREAT_PATTERN (which would risk pathological backtracking).
THREAT_PATTERN_REVERSED = re.compile(
    r"\b(sinut|sut|teid[aä]t|h[aä]net)\s+(min[aä]\s+)?"
    r"(tap(?:an|aisin|oin)|hakkaan|tuhoan|vahingoitan)\b",
    re.IGNORECASE,
)

BLOCKED_PATTERNS: tuple[re.Pattern[str], ...] = (
    SLUR_PATTERN,
    SEXUAL_INSULT_PATTERN,
    THREAT_PATTERN,
    THREAT_PATTERN_REVERSED,
)


def apply_content_policy(text: str) -> str:
    if not text:
        return text

    for pattern in BLOCKED_PATTERNS:
        if pattern.search(text):
            return CONTENT_POLICY_PLACEHOLDER

    return text
