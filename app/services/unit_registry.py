from __future__ import annotations

import re
import unicodedata
from typing import Iterable, List, Optional

from app.models.reservation import Unit

# To add or update units, change this registry entry only. Keep unit_id stable because
# callers and conversation logs may store it.
UNITS: tuple[Unit, ...] = (
    Unit(
        unit_id="hostelli-framinranta",
        display_name="Hostelli Framinranta",
        area="Framinranta",
        capacity=2,
        nightly_rate_eur=69,
        min_nights=2,
    ),
    Unit(
        unit_id="huoneistohotelli-framinranta",
        display_name="Huoneistohotelli Framinranta",
        area="Framinranta",
        capacity=2,
        nightly_rate_eur=102,
        min_nights=1,
    ),
    Unit(
        unit_id="jokipuistopark-asunto-1",
        display_name="Jokipuistopark asunto 1",
        area="Jokipuisto",
        capacity=5,
        nightly_rate_eur=145,
        min_nights=1,
    ),
    Unit(
        unit_id="jokipuistopark-asunto-2",
        display_name="Jokipuistopark asunto 2",
        area="Jokipuisto",
        capacity=4,
        nightly_rate_eur=138,
        min_nights=1,
    ),
    Unit(
        unit_id="jokipuistopark-asunto-3",
        display_name="Jokipuistopark asunto 3",
        area="Jokipuisto",
        capacity=5,
        nightly_rate_eur=168,
        min_nights=1,
    ),
    Unit(
        unit_id="ranta-hostelli",
        display_name="Hotelli Frami Ranta-Hostelli",
        area="Jokipuisto",
        capacity=2,
        nightly_rate_eur=55,
        min_nights=2,
    ),
    Unit(
        unit_id="kampusaukio-7-asunto-1",
        display_name="Kampusaukio 7, asunto 1",
        area="Kampusaukio",
        capacity=4,
        nightly_rate_eur=149,
        min_nights=1,
    ),
    Unit(
        unit_id="kampusaukio-7-asunto-2",
        display_name="Kampusaukio 7, asunto 2",
        area="Kampusaukio",
        capacity=2,
        nightly_rate_eur=115,
        min_nights=1,
    ),
    Unit(
        unit_id="kampusaukio-7-asunto-4",
        display_name="Kampusaukio 7, asunto 4",
        area="Kampusaukio",
        capacity=4,
        nightly_rate_eur=149,
        min_nights=1,
    ),
    Unit(
        unit_id="kampusaukio-7-asunto-5",
        display_name="Kampusaukio 7, asunto 5",
        area="Kampusaukio",
        capacity=2,
        nightly_rate_eur=121,
        min_nights=1,
    ),
    Unit(
        unit_id="kampusaukio-7-asunto-6",
        display_name="Kampusaukio 7, asunto 6",
        area="Kampusaukio",
        capacity=4,
        nightly_rate_eur=149,
        min_nights=1,
    ),
    Unit(
        unit_id="kampusaukio-7-asunto-7",
        display_name="Kampusaukio 7, asunto 7",
        area="Kampusaukio",
        capacity=4,
        nightly_rate_eur=165,
        min_nights=1,
    ),
    Unit(
        unit_id="framinranta-huone-7-kampusnurkka",
        display_name="Framinranta, huone 7 kampusnurkka",
        area="Framinranta",
        capacity=4,
        nightly_rate_eur=112,
        min_nights=2,
    ),
)

AREA_ALIASES = {
    "framinranta": "Framinranta",
    "kampusaukio": "Kampusaukio",
    "jokipuisto": "Jokipuisto",
    "any": None,
}


def get_all_units() -> List[Unit]:
    return list(UNITS)


def find_unit(unit_id: str) -> Optional[Unit]:
    normalized = unit_id.strip().lower()
    for unit in UNITS:
        if unit.unit_id.lower() == normalized:
            return unit
    return None


def normalize_area(area: Optional[str]) -> Optional[str]:
    if area is None:
        return None
    cleaned = area.strip().lower()
    if not cleaned:
        return None
    return AREA_ALIASES.get(cleaned, area.strip())


def find_units_by_name(unit_name: str, *, area: Optional[str] = None) -> List[Unit]:
    normalized_query = _normalize_match_text(unit_name)
    if not normalized_query:
        return []

    candidates = get_all_units()
    normalized_area = normalize_area(area)
    if normalized_area:
        candidates = [unit for unit in candidates if unit.area == normalized_area]

    scored: list[tuple[int, Unit]] = []
    for unit in candidates:
        score = _score_unit_name_match(unit, normalized_query)
        if score > 0:
            scored.append((score, unit))

    if not scored:
        return []

    best_score = max(score for score, _ in scored)
    return [unit for score, unit in scored if score == best_score]


def select_units(
    *,
    unit_id: Optional[str],
    unit_name: Optional[str],
    area: Optional[str],
) -> List[Unit]:
    if unit_id:
        unit = find_unit(unit_id)
        return [unit] if unit else []

    if unit_name:
        matched = find_units_by_name(unit_name, area=area)
        if matched:
            return matched

    normalized_area = normalize_area(area)
    if not normalized_area:
        return get_all_units()

    return [unit for unit in UNITS if unit.area == normalized_area]


def unit_ids(units: Iterable[Unit]) -> List[str]:
    return [unit.unit_id for unit in units]


def _normalize_match_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    alnum_only = re.sub(r"[^a-z0-9]+", " ", without_marks.lower())
    return re.sub(r"\s+", " ", alnum_only).strip()


def _match_aliases(unit: Unit) -> List[str]:
    aliases = {
        unit.display_name,
        unit.unit_id,
        unit.display_name.replace(",", " "),
    }
    return [_normalize_match_text(alias) for alias in aliases if alias]


def _score_unit_name_match(unit: Unit, normalized_query: str) -> int:
    query_tokens = set(normalized_query.split())
    if not query_tokens:
        return 0

    best_score = 0
    for alias in _match_aliases(unit):
        alias_tokens = set(alias.split())
        if normalized_query == alias:
            best_score = max(best_score, 100)
            continue
        if query_tokens == alias_tokens:
            best_score = max(best_score, 95)
            continue
        if normalized_query in alias or alias in normalized_query:
            best_score = max(best_score, 80)
        if query_tokens.issubset(alias_tokens):
            best_score = max(best_score, 70 + len(query_tokens))

    return best_score
