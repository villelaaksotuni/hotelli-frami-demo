from datetime import date, timedelta
import logging
from typing import Any, Dict, Iterable, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from app.models.availability import (
    AvailabilityOption,
    AvailabilityQuery,
    AvailabilityResponse,
    AvailabilityStatus,
    AvailableDuration,
    BookingOnlineUnit,
)
from app.models.call import utc_now_iso
from app.services.availability_registry import normalize_area, select_units
from app.services.bookingonline_fetcher import (
    BookingOnlineCalendarFetcher,
    BookingOnlineFetchError,
)
from app.services.bookingonline_parser import (
    ParsedCalendarPage,
    format_finnish_date,
    parse_calendar_html,
)

logger = logging.getLogger(__name__)


class AvailabilityValidationError(ValueError):
    pass


class BookingOnlineAvailabilityChecker:
    def __init__(self, fetcher: Optional[BookingOnlineCalendarFetcher] = None) -> None:
        self.fetcher = fetcher or BookingOnlineCalendarFetcher()

    async def check(self, payload: Dict[str, Any]) -> AvailabilityResponse:
        query = validate_availability_payload(payload)
        units = select_units(unit_id=query.unit_id, unit_name=query.unit_name, area=query.area)
        scraped_at = utc_now_iso()

        if not units:
            return AvailabilityResponse(
                status="unknown",
                confidence="low",
                scraped_at=scraped_at,
                source="bookingonline_calendar_html",
                query=query,
                options=[],
                booking_not_confirmed=True,
                message_for_assistant="En löytänyt pyydettyyn kohteeseen sopivaa varauskalenteria.",
                error_code="unit_not_found",
            )

        options = [await self._check_unit(unit, query) for unit in units]
        status = _aggregate_status(option.status for option in options)
        return AvailabilityResponse(
            status=status,
            confidence=_confidence_for(status, options),
            scraped_at=scraped_at,
            source="bookingonline_calendar_html",
            query=query,
            options=options,
            booking_not_confirmed=True,
            message_for_assistant=_build_assistant_message(status, query, options),
            error_code=None if status != "unknown" else "calendar_uninterpretable",
        )

    async def _check_unit(
        self,
        unit: BookingOnlineUnit,
        query: AvailabilityQuery,
    ) -> AvailabilityOption:
        try:
            html = await self.fetcher.fetch_calendar_html(
                unit,
                arrival_date=date.fromisoformat(query.arrival_date),
                guests=query.guests,
            )
            page = parse_calendar_html(html)
        except (BookingOnlineFetchError, ValueError) as exc:
            logger.warning(
                "Availability check failed unit_id=%s arrival_date=%s nights=%s guests=%s error=%s",
                unit.unitId,
                query.arrival_date,
                query.nights,
                query.guests,
                exc,
            )
            return _unknown_option(unit, "BookingOnline calendar could not be loaded.")

        return interpret_calendar_page(unit, query, page)


def validate_availability_payload(payload: Dict[str, Any]) -> AvailabilityQuery:
    try:
        arrival_date = date.fromisoformat(str(payload.get("arrivalDate", "")))
    except ValueError as exc:
        raise AvailabilityValidationError("arrivalDate must be YYYY-MM-DD") from exc

    nights = _read_positive_int(payload.get("nights"), "nights", max_value=60)
    guests = _read_positive_int(payload.get("guests"), "guests", max_value=30)
    area = normalize_area(payload.get("area"))
    unit_id = payload.get("unitId")
    unit_id = str(unit_id).strip() if unit_id else None
    unit_name = payload.get("unitName")
    unit_name = " ".join(str(unit_name or "").split()).strip() or None
    departure_date = arrival_date + timedelta(days=nights)

    return AvailabilityQuery(
        arrival_date=arrival_date.isoformat(),
        departure_date=departure_date.isoformat(),
        nights=nights,
        guests=guests,
        area=area,
        unit_id=unit_id,
        unit_name=unit_name,
    )


def interpret_calendar_page(
    unit: BookingOnlineUnit,
    query: AvailabilityQuery,
    page: ParsedCalendarPage,
) -> AvailabilityOption:
    if not page.has_core_calendar_schema:
        return _unknown_option(unit, "BookingOnline HTML schema did not contain expected calendar data.")

    arrival_date = date.fromisoformat(query.arrival_date)
    date_cell = page.date_cells.get(arrival_date)
    if not date_cell:
        return _unknown_option(unit, "Requested arrival date was not present in the loaded calendar month.")

    if not date_cell.is_selectable_arrival:
        return AvailabilityOption(
            unit_id=unit.unitId,
            name=page.product_name or unit.displayName,
            area=unit.area,
            tuote_id=unit.tuoteId,
            calendar_url=unit.calendarUrl,
            status="not_selectable",
            reason="Requested arrival date is not selectable in the BookingOnline calendar.",
        )

    if page.guest_counts and query.guests not in page.guest_counts:
        return AvailabilityOption(
            unit_id=unit.unitId,
            name=page.product_name or unit.displayName,
            area=unit.area,
            tuote_id=unit.tuoteId,
            calendar_url=unit.calendarUrl,
            status="guest_count_unavailable",
            available_durations=_available_durations(page),
            reason="Requested guest count is not listed in the BookingOnline guest selector.",
        )

    if not page.guest_counts or not page.durations:
        return _unknown_option(unit, "BookingOnline HTML did not contain expected guest or duration options.")

    matching_duration = next(
        (duration for duration in page.durations if duration.nights == query.nights),
        None,
    )
    available_durations = _available_durations(page)
    if not matching_duration:
        return AvailabilityOption(
            unit_id=unit.unitId,
            name=page.product_name or unit.displayName,
            area=unit.area,
            tuote_id=unit.tuoteId,
            calendar_url=unit.calendarUrl,
            status="duration_unavailable",
            available_durations=available_durations,
            reason="Requested stay length is not listed in the BookingOnline duration selector.",
        )

    if matching_duration.price_total is None:
        return _unknown_option(unit, "Requested duration was listed, but the price could not be parsed.")

    return AvailabilityOption(
        unit_id=unit.unitId,
        name=page.product_name or unit.displayName,
        area=unit.area,
        tuote_id=unit.tuoteId,
        calendar_url=unit.calendarUrl,
        status="available",
        price_total=matching_duration.price_total,
        currency="EUR",
        booking_url=build_booking_url(
            unit,
            page,
            arrival_date=arrival_date,
            guests=query.guests,
            nights=query.nights,
        ),
        available_durations=available_durations,
        reason="BookingOnline calendar currently shows the requested date, guest count, and duration as selectable.",
    )


def build_booking_url(
    unit: BookingOnlineUnit,
    page: ParsedCalendarPage,
    *,
    arrival_date: date,
    guests: int,
    nights: int,
) -> str:
    fallback_url = "https://booking.hotelliframi.invalid/VarausSv?kieli=FIN"
    source_url = page.booking_form_action or fallback_url
    parsed = urlparse(source_url)
    query_values = dict(parse_qsl(parsed.query, keep_blank_values=True))
    arrival = format_finnish_date(arrival_date)
    query_values.update(
        {
            "kieli": query_values.get("kieli", "FIN"),
            "tuote_id": unit.tuoteId,
            "pvm": arrival,
            "alku": arrival,
            "hlo": str(guests),
            "kesto": str(nights),
        }
    )
    return urlunparse(parsed._replace(query=urlencode(query_values)))


def _available_durations(page: ParsedCalendarPage) -> list[AvailableDuration]:
    return [
        AvailableDuration(
            nights=duration.nights,
            price_total=duration.price_total,
            currency="EUR",
            raw_label=duration.raw_label,
        )
        for duration in page.durations
        if duration.price_total is not None
    ]


def _unknown_option(unit: BookingOnlineUnit, reason: str) -> AvailabilityOption:
    return AvailabilityOption(
        unit_id=unit.unitId,
        name=unit.displayName,
        area=unit.area,
        tuote_id=unit.tuoteId,
        calendar_url=unit.calendarUrl,
        status="unknown",
        reason=reason,
    )


def _read_positive_int(value: Any, field_name: str, *, max_value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise AvailabilityValidationError(f"{field_name} must be a positive integer") from exc
    if parsed <= 0 or parsed > max_value:
        raise AvailabilityValidationError(f"{field_name} must be between 1 and {max_value}")
    return parsed


def _aggregate_status(statuses: Iterable[AvailabilityStatus]) -> AvailabilityStatus:
    status_list = list(statuses)
    if not status_list:
        return "unknown"
    if any(status == "available" for status in status_list):
        return "available"
    if any(status == "duration_unavailable" for status in status_list):
        return "duration_unavailable"
    if any(status == "unknown" for status in status_list):
        return "unknown"
    if any(status == "guest_count_unavailable" for status in status_list):
        return "guest_count_unavailable"
    if any(status == "not_selectable" for status in status_list):
        return "not_selectable"
    return "unavailable"


def _confidence_for(status: AvailabilityStatus, options: list[AvailabilityOption]) -> str:
    if status == "available":
        return "high"
    if options and all(option.status != "unknown" for option in options):
        return "medium"
    return "low"


def _build_assistant_message(
    status: AvailabilityStatus,
    query: AvailabilityQuery,
    options: list[AvailabilityOption],
) -> str:
    available = [option for option in options if option.status == "available"]
    if available:
        first = available[0]
        return (
            f"BookingOnline-kalenterissa näkyy saatavuutta kohteessa {first.name} "
            f"{query.arrival_date} alkaen {query.nights} yöksi, {query.guests} hengelle. "
            f"Kokonaishinta on {first.price_total} euroa. Varausta ei ole vielä vahvistettu."
        )

    if status == "duration_unavailable":
        alternatives = sorted(
            {
                duration.nights
                for option in options
                for duration in option.available_durations
            }
        )
        alternative_text = ", ".join(str(value) for value in alternatives[:6])
        suffix = f" Kalenterissa näkyvät kestot ovat: {alternative_text} yötä." if alternative_text else ""
        return (
            f"Tulopäivä {query.arrival_date} näkyy valittavana, mutta {query.nights} yön "
            f"kestoa ei näy saatavilla.{suffix} Varausta ei ole vahvistettu."
        )

    if status == "guest_count_unavailable":
        return (
            f"Pyydettyä henkilömäärää {query.guests} ei näy valittavana tarkistetuissa "
            "BookingOnline-kalentereissa. Varausta ei ole vahvistettu."
        )

    if status == "not_selectable":
        return (
            f"Tulopäivä {query.arrival_date} ei näy valittavana aloituspäivänä "
            "tarkistetuissa BookingOnline-kalentereissa."
        )

    return (
        "En pysty tulkitsemaan BookingOnline-kalenterin saatavuutta luotettavasti juuri nyt. "
        "Älä lupaa saatavuutta tai hintaa vahvistettuna."
    )


availability_checker = BookingOnlineAvailabilityChecker()
