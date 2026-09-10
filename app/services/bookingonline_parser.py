from dataclasses import dataclass, field
from datetime import date, datetime
from html import unescape
from html.parser import HTMLParser
import re
from typing import Dict, List, Optional
from urllib.parse import urljoin

BOOKINGONLINE_BASE_URL = "https://booking.hotelliframi.invalid/"


@dataclass(frozen=True)
class CalendarDateCell:
    date: date
    classes: set[str]

    @property
    def is_selectable_arrival(self) -> bool:
        return "kalenteri_paiva" in self.classes and "kielletty" not in self.classes


@dataclass(frozen=True)
class ParsedDurationOption:
    nights: int
    price_total: Optional[int]
    currency: Optional[str]
    raw_label: str


@dataclass
class ParsedCalendarPage:
    product_name: Optional[str] = None
    date_cells: Dict[date, CalendarDateCell] = field(default_factory=dict)
    guest_counts: List[int] = field(default_factory=list)
    durations: List[ParsedDurationOption] = field(default_factory=list)
    booking_form_action: Optional[str] = None

    @property
    def has_core_calendar_schema(self) -> bool:
        return bool(self.product_name and self.date_cells)


class BookingOnlineCalendarParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.page = ParsedCalendarPage()
        self._tag_stack: list[str] = []
        self._capture_h1 = False
        self._h1_parts: list[str] = []
        self._active_select_id: Optional[str] = None
        self._active_option_value: Optional[str] = None
        self._option_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        attr_map = {name: value or "" for name, value in attrs}
        self._tag_stack.append(tag)

        if tag == "h1":
            self._capture_h1 = True
            self._h1_parts = []
            return

        if tag == "td" and "kalenteri_paiva" in attr_map.get("class", "").split():
            parsed_date = parse_finnish_date(attr_map.get("paivamaara"))
            if parsed_date:
                classes = set(attr_map.get("class", "").split())
                self.page.date_cells[parsed_date] = CalendarDateCell(
                    date=parsed_date,
                    classes=classes,
                )
            return

        if tag == "select":
            select_id = attr_map.get("id") or attr_map.get("name")
            if select_id in {"hlo", "kesto"}:
                self._active_select_id = select_id
            return

        if tag == "option" and self._active_select_id:
            self._active_option_value = attr_map.get("value")
            self._option_parts = []
            return

        if tag == "form" and attr_map.get("id") == "bookingDForm":
            action = attr_map.get("action")
            if action:
                self.page.booking_form_action = urljoin(BOOKINGONLINE_BASE_URL, action)

    def handle_endtag(self, tag: str) -> None:
        if tag == "h1" and self._capture_h1:
            product_name = normalize_whitespace(" ".join(self._h1_parts))
            self.page.product_name = product_name or None
            self._capture_h1 = False
            self._h1_parts = []

        if tag == "option" and self._active_select_id and self._active_option_value is not None:
            label = normalize_whitespace(" ".join(self._option_parts))
            if self._active_select_id == "hlo":
                guest_count = parse_int(self._active_option_value)
                if guest_count is not None:
                    self.page.guest_counts.append(guest_count)
            elif self._active_select_id == "kesto":
                duration = parse_duration_option(self._active_option_value, label)
                if duration:
                    self.page.durations.append(duration)
            self._active_option_value = None
            self._option_parts = []

        if tag == "select":
            self._active_select_id = None

        if self._tag_stack:
            self._tag_stack.pop()

    def handle_data(self, data: str) -> None:
        if self._capture_h1:
            self._h1_parts.append(data)
        if self._active_option_value is not None:
            self._option_parts.append(data)


def parse_calendar_html(html: str) -> ParsedCalendarPage:
    parser = BookingOnlineCalendarParser()
    parser.feed(html)
    return parser.page


def parse_finnish_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%d.%m.%Y").date()
    except ValueError:
        return None


def format_finnish_date(value: date) -> str:
    return value.strftime("%d.%m.%Y")


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(value).replace("\xa0", " ")).strip()


def parse_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_duration_option(value: Optional[str], label: str) -> Optional[ParsedDurationOption]:
    nights = parse_int(value)
    if nights is None:
        match = re.search(r"(\d+)\s*vrk", normalize_whitespace(label), flags=re.IGNORECASE)
        nights = int(match.group(1)) if match else None
    if nights is None:
        return None

    price_total = parse_eur_price(label)
    return ParsedDurationOption(
        nights=nights,
        price_total=price_total,
        currency="EUR" if price_total is not None else None,
        raw_label=normalize_whitespace(label),
    )


def parse_eur_price(label: str) -> Optional[int]:
    cleaned = normalize_whitespace(label)
    match = re.search(r"(\d[\d\s\xa0]*)\s*€", cleaned)
    if not match:
        return None
    digits = re.sub(r"\s+", "", match.group(1).replace("\xa0", " "))
    try:
        return int(digits)
    except ValueError:
        return None
