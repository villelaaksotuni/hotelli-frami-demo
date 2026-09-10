from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Literal, Optional

ReservationStatus = Literal[
    "confirmed",
    "unavailable",
    "already_reserved_for_stay",
    "unit_not_found",
    "invalid_request",
]

AvailabilityStatus = Literal[
    "available",
    "unavailable",
    "not_selectable",
    "guest_count_unavailable",
    "duration_unavailable",
    "unknown",
]

Confidence = Literal["high", "medium", "low"]


class ReservationValidationError(ValueError):
    """Raised when create-reservation input fails validation."""


@dataclass(frozen=True)
class Unit:
    unit_id: str
    display_name: str
    area: str
    capacity: int
    nightly_rate_eur: int
    min_nights: int = 1
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Reservation:
    reservation_id: str
    unit_id: str
    unit_name: str
    area: str
    arrival_date: str
    departure_date: str
    nights: int
    guests: int
    price_total: int
    currency: Literal["EUR"]
    created_at: str
    expires_at: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CreateReservationResult:
    status: ReservationStatus
    source: Literal["synthetic_reservation_store"]
    demo_reservation: bool
    reservation: Optional[Reservation]
    message_for_assistant: str
    error_code: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "source": self.source,
            "demo_reservation": self.demo_reservation,
            "reservation": self.reservation.to_dict() if self.reservation is not None else None,
            "message_for_assistant": self.message_for_assistant,
            "error_code": self.error_code,
        }


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
    price_total: Optional[int] = None
    currency: Optional[Literal["EUR"]] = None
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
    source: Literal["synthetic_reservation_store"]
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
