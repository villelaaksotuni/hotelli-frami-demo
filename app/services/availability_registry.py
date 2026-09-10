import os
import re
import unicodedata
from typing import Iterable, List, Optional
from urllib.parse import urlencode

from app.models.availability import BookingOnlineUnit

BOOKINGONLINE_CALENDAR_BASE_URL = os.getenv(
    "BOOKINGONLINE_CALENDAR_BASE_URL",
    "https://booking.hotelliframi.invalid/stable/integroitukalenteri.jsp",
)
DEFAULT_TEEMA_ID = os.getenv("BOOKINGONLINE_TEEMA_ID", "9101")
DEFAULT_MYYJA_ID = os.getenv("BOOKINGONLINE_MYYJA_ID", "9202")
DEFAULT_LANGUAGE = "FIN"


def _calendar_url(kiintea_tuote_id: str) -> str:
    query = urlencode(
        {
            "teema_id": DEFAULT_TEEMA_ID,
            "kiintea_tuote_id": kiintea_tuote_id,
            "myyja_id": DEFAULT_MYYJA_ID,
            "kieli": DEFAULT_LANGUAGE,
        }
    )
    return f"{BOOKINGONLINE_CALENDAR_BASE_URL}?{query}"


def _unit(
    unit_id: str,
    display_name: str,
    area: str,
    kiintea_tuote_id: str,
    notes: Optional[str] = None,
) -> BookingOnlineUnit:
    return BookingOnlineUnit(
        unitId=unit_id,
        displayName=display_name,
        area=area,
        teemaId=DEFAULT_TEEMA_ID,
        myyjaId=DEFAULT_MYYJA_ID,
        kiinteaTuoteId=kiintea_tuote_id,
        tuoteId=f"{DEFAULT_MYYJA_ID}-{kiintea_tuote_id}",
        calendarUrl=_calendar_url(kiintea_tuote_id),
        notes=notes,
    )


# To add or update units, change this registry entry only. Keep unitId stable because
# callers and conversation logs may store it.
BOOKINGONLINE_UNITS: tuple[BookingOnlineUnit, ...] = (
    _unit("hostelli-framinranta", "Hostelli Framinranta", "Framinranta", "51001"),
    _unit("huoneistohotelli-framinranta", "Huoneistohotelli Framinranta", "Framinranta", "51002"),
    _unit("jokipuistopark-asunto-1", "Jokipuistopark asunto 1", "Jokipuisto", "51003"),
    _unit("jokipuistopark-asunto-2", "Jokipuistopark asunto 2", "Jokipuisto", "51004"),
    _unit("jokipuistopark-asunto-3", "Jokipuistopark asunto 3", "Jokipuisto", "51005"),
    _unit("ranta-hostelli", "Hotelli Frami Ranta-Hostelli", "Jokipuisto", "51006"),
    _unit("kampusaukio-7-asunto-1", "Kampusaukio 7, asunto 1", "Kampusaukio", "51007"),
    _unit("kampusaukio-7-asunto-2", "Kampusaukio 7, asunto 2", "Kampusaukio", "51008"),
    _unit("kampusaukio-7-asunto-4", "Kampusaukio 7, asunto 4", "Kampusaukio", "51009"),
    _unit("kampusaukio-7-asunto-5", "Kampusaukio 7, asunto 5", "Kampusaukio", "51010"),
    _unit("kampusaukio-7-asunto-6", "Kampusaukio 7, asunto 6", "Kampusaukio", "51011"),
    _unit("kampusaukio-7-asunto-7", "Kampusaukio 7, asunto 7", "Kampusaukio", "51012"),
    _unit(
        "framinranta-huone-7-kampusnurkka",
        "Framinranta, huone 7 kampusnurkka",
        "Framinranta",
        "51013",
    ),
)

AREA_ALIASES = {
    "framinranta": "Framinranta",
    "kampusaukio": "Kampusaukio",
    "jokipuisto": "Jokipuisto",
    "any": None,
}


def get_all_units() -> List[BookingOnlineUnit]:
    return list(BOOKINGONLINE_UNITS)


def find_unit(unit_id: str) -> Optional[BookingOnlineUnit]:
    normalized = unit_id.strip().lower()
    for unit in BOOKINGONLINE_UNITS:
        if unit.unitId.lower() == normalized:
            return unit
    return None


def find_unit_by_tuote_id(tuote_id: str) -> Optional[BookingOnlineUnit]:
    normalized = tuote_id.strip()
    for unit in BOOKINGONLINE_UNITS:
        if unit.tuoteId == normalized:
            return unit
    return None


def normalize_area(area: Optional[str]) -> Optional[str]:
    if area is None:
        return None
    cleaned = area.strip().lower()
    if not cleaned:
        return None
    return AREA_ALIASES.get(cleaned, area.strip())


def find_units_by_name(unit_name: str, *, area: Optional[str] = None) -> List[BookingOnlineUnit]:
    normalized_query = _normalize_match_text(unit_name)
    if not normalized_query:
        return []

    candidates = get_all_units()
    normalized_area = normalize_area(area)
    if normalized_area:
        candidates = [unit for unit in candidates if unit.area == normalized_area]

    scored: list[tuple[int, BookingOnlineUnit]] = []
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
) -> List[BookingOnlineUnit]:
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

    return [unit for unit in BOOKINGONLINE_UNITS if unit.area == normalized_area]


def unit_ids(units: Iterable[BookingOnlineUnit]) -> List[str]:
    return [unit.unitId for unit in units]


def _normalize_match_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    alnum_only = re.sub(r"[^a-z0-9]+", " ", without_marks.lower())
    return re.sub(r"\s+", " ", alnum_only).strip()


def _match_aliases(unit: BookingOnlineUnit) -> List[str]:
    aliases = {
        unit.displayName,
        unit.unitId,
        unit.displayName.replace(",", " "),
    }
    return [_normalize_match_text(alias) for alias in aliases if alias]


def _score_unit_name_match(unit: BookingOnlineUnit, normalized_query: str) -> int:
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
