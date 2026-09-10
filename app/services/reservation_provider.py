from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any, Optional, Protocol

from app.config.settings import settings
from app.models.call import CallSession
from app.models.reservation import (
    CreateReservationResult,
    Reservation,
    ReservationValidationError,
)
from app.services.synthetic_reservation_store import SyntheticReservationStore

__all__ = ["ReservationProvider", "reservation_provider", "ReservationValidationError"]


class ReservationProvider(Protocol):
    async def create_reservation(
        self,
        payload: dict[str, Any],
        *,
        session: Optional[CallSession] = None,
    ) -> CreateReservationResult: ...

    def list_active_reservations(self) -> list[Reservation]: ...


reservation_provider: ReservationProvider = SyntheticReservationStore(
    storage_path=Path(settings.reservation_store_path),
    ttl=timedelta(hours=settings.reservation_ttl_hours),
    max_per_call=settings.max_reservations_per_call,
)
