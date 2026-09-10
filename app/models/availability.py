from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Literal, Optional

AvailabilityStatus = Literal[
    "available",
    "unavailable",
    "not_selectable",
    "guest_count_unavailable",
    "duration_unavailable",
    "unknown",
]

Confidence = Literal["high", "medium", "low"]


@dataclass(frozen=True)
class BookingOnlineUnit:
    unitId: str
    displayName: str
    area: str
    teemaId: str
    myyjaId: str
    kiinteaTuoteId: str
    tuoteId: str
    calendarUrl: Optional[str] = None
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AvailabilityQuery:
    arrival_date: str
    departure_date: str
    nights: int
    guests: int
    area: Optional[str] = None
    unit_id: Optional[str] = None
    unit_name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AvailableDuration:
    nights: int
    price_total: int
    currency: Literal["EUR"]
    raw_label: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AvailabilityOption:
    unit_id: str
    name: str
    area: str
    status: AvailabilityStatus
    tuote_id: Optional[str] = None
    calendar_url: Optional[str] = None
    price_total: Optional[int] = None
    currency: Optional[Literal["EUR"]] = None
    booking_url: Optional[str] = None
    available_durations: List[AvailableDuration] = field(default_factory=list)
    reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["available_durations"] = [
            duration.to_dict() for duration in self.available_durations
        ]
        return payload


@dataclass(frozen=True)
class AvailabilityResponse:
    status: AvailabilityStatus
    confidence: Confidence
    scraped_at: str
    source: Literal["bookingonline_calendar_html"]
    query: AvailabilityQuery
    options: List[AvailabilityOption]
    booking_not_confirmed: bool
    message_for_assistant: str
    error_code: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "confidence": self.confidence,
            "scraped_at": self.scraped_at,
            "source": self.source,
            "query": self.query.to_dict(),
            "options": [option.to_dict() for option in self.options],
            "booking_not_confirmed": self.booking_not_confirmed,
            "message_for_assistant": self.message_for_assistant,
            "error_code": self.error_code,
        }
