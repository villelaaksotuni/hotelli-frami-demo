from __future__ import annotations

from typing import Any, Optional


def extract_live_call_origin_phone(metadata: dict[str, Any]) -> Optional[str]:
    return normalize_phone(metadata.get("from_number"))


def extract_counterparty_phone(metadata: dict[str, Any]) -> Optional[str]:
    direction = str(metadata.get("direction") or "").strip().lower()
    if direction == "outbound":
        return normalize_phone(metadata.get("to_number"))
    if direction == "inbound":
        return normalize_phone(metadata.get("from_number"))
    return normalize_phone(metadata.get("to_number") or metadata.get("from_number"))


def normalize_phone(value: Any) -> Optional[str]:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.startswith("+"):
        digits = "+" + "".join(ch for ch in raw[1:] if ch.isdigit())
    else:
        digits = "".join(ch for ch in raw if ch.isdigit())
    return digits if len(digits.replace("+", "")) >= 7 else None
