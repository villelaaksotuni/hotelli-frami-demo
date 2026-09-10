import asyncio
from datetime import date
import logging
from typing import Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.models.availability import BookingOnlineUnit
from app.services.bookingonline_parser import format_finnish_date

logger = logging.getLogger(__name__)

BOOKINGONLINE_TIMEOUT_SECONDS = 8
BOOKINGONLINE_USER_AGENT = "HotelliFramiAvailabilityChecker/1.0"


class BookingOnlineFetchError(RuntimeError):
    pass


class BookingOnlineCalendarFetcher:
    async def fetch_calendar_html(
        self,
        unit: BookingOnlineUnit,
        *,
        arrival_date: date,
        guests: int,
    ) -> str:
        return await asyncio.to_thread(
            self._fetch_calendar_html_sync,
            unit,
            arrival_date,
            guests,
        )

    def _fetch_calendar_html_sync(
        self,
        unit: BookingOnlineUnit,
        arrival_date: date,
        guests: int,
    ) -> str:
        if not unit.calendarUrl:
            raise BookingOnlineFetchError(f"Unit {unit.unitId} is missing calendarUrl")

        arrival = format_finnish_date(arrival_date)
        body = urlencode(
            {
                "pvm": arrival,
                "alku": arrival,
                "hlo": str(guests),
                "k_kk": str(arrival_date.month),
                "k_v": str(arrival_date.year),
            }
        ).encode("utf-8")
        request = Request(
            unit.calendarUrl,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": BOOKINGONLINE_USER_AGENT,
            },
        )

        try:
            with urlopen(request, timeout=BOOKINGONLINE_TIMEOUT_SECONDS) as response:
                raw_body = response.read()
                charset = _extract_charset(response.headers.get("Content-Type")) or "utf-8"
                return raw_body.decode(charset, errors="replace")
        except Exception as exc:
            logger.warning(
                "BookingOnline fetch failed unit_id=%s arrival_date=%s guests=%s error=%s",
                unit.unitId,
                arrival_date.isoformat(),
                guests,
                exc,
            )
            raise BookingOnlineFetchError(str(exc)) from exc


def _extract_charset(content_type: Optional[str]) -> Optional[str]:
    if not content_type:
        return None
    for part in content_type.split(";"):
        key, _, value = part.strip().partition("=")
        if key.lower() == "charset" and value:
            return value.strip()
    return None
