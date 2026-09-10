from __future__ import annotations

from typing import Any

TOPIC_LABELS_FI = {
    "booking": "varaus",
    "availability": "saatavuus",
    "pricing": "hinta",
    "check_in_out": "sisään- ja uloskirjautuminen",
    "cancellation": "peruutus",
    "pets": "lemmikit",
    "parking": "pysäköinti",
    "breakfast": "aamiainen",
}

TOPIC_ALIASES = {
    "booking": (
        "booking",
        "book",
        "reserve",
        "reservation",
        "room booking",
        "varaa",
        "varaus",
        "huonevaraus",
        "majoitusvaraus",
    ),
    "availability": (
        "availability",
        "available",
        "room availability",
        "saatavuus",
        "vapaa huone",
        "vapaat huoneet",
        "huone",
        "huoneet",
        "mökki",
        "mokki",
        "apartment",
    ),
    "pricing": (
        "price",
        "pricing",
        "rate",
        "cost",
        "hinta",
        "hinnat",
        "hinnoittelu",
        "maksu",
    ),
    "check_in_out": (
        "check in",
        "check-in",
        "check out",
        "check-out",
        "sisäänkirjautuminen",
        "sisään- ja uloskirjautuminen",
        "uloskirjautuminen",
        "saapuminen",
        "lähtöaika",
    ),
    "cancellation": (
        "cancel",
        "cancellation",
        "peruut",
        "peruutus",
        "peruminen",
    ),
    "pets": (
        "pet",
        "dog",
        "cat",
        "lemmik",
        "lemmikit",
        "koira",
        "kissa",
    ),
    "parking": (
        "parking",
        "parkki",
        "pysäköinti",
        "pysakointi",
        "autopaikka",
    ),
    "breakfast": (
        "breakfast",
        "aamupala",
        "aamiainen",
    ),
}


def topic_label_fi(topic_key: str) -> str:
    return TOPIC_LABELS_FI.get(topic_key, topic_key)


def normalize_topic_key(value: Any) -> str | None:
    normalized = _normalize_text(value)
    if not normalized:
        return None

    for topic_key, aliases in TOPIC_ALIASES.items():
        if normalized == topic_key:
            return topic_key
        if normalized == _normalize_text(TOPIC_LABELS_FI.get(topic_key)):
            return topic_key
        if any(normalized == _normalize_text(alias) for alias in aliases):
            return topic_key
    return None


def normalize_topic_keys(values: Any) -> list[str]:
    topic_keys: list[str] = []
    for value in values or []:
        topic_key = normalize_topic_key(value)
        if topic_key and topic_key not in topic_keys:
            topic_keys.append(topic_key)
    return topic_keys[:6]


def infer_topic_keys(text: Any) -> list[str]:
    normalized_text = _normalize_text(text)
    if not normalized_text:
        return []

    topic_keys: list[str] = []
    for topic_key, aliases in TOPIC_ALIASES.items():
        keywords = [topic_key, TOPIC_LABELS_FI.get(topic_key, ""), *aliases]
        if any(_normalize_text(keyword) in normalized_text for keyword in keywords if keyword):
            topic_keys.append(topic_key)
    return topic_keys[:6]


def to_finnish_topic_labels(values: Any) -> list[str]:
    topic_labels: list[str] = []
    for value in values or []:
        topic_key = normalize_topic_key(value)
        label = topic_label_fi(topic_key) if topic_key else _clean_text(value)
        if label and label not in topic_labels:
            topic_labels.append(label)
    return topic_labels[:6]


def _normalize_text(value: Any) -> str:
    return _clean_text(value).casefold()


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()
