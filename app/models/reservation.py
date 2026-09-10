from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Literal, Optional

ReservationStatus = Literal[
    "confirmed",
    "unavailable",
    "already_reserved_for_stay",
    "unit_not_found",
    "invalid_request",
]


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
