from __future__ import annotations

from typing import List, Optional

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
