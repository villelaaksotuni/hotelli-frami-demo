from __future__ import annotations

import json
import logging
import threading
import uuid
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Optional

from app.models.call import CallSession
from app.models.reservation import (
    CreateReservationResult,
    Reservation,
    ReservationValidationError,
)
from app.services import unit_registry

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_positive_int(value: Any, field_name: str, *, max_value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ReservationValidationError(f"{field_name} must be a positive integer") from exc
    if parsed <= 0 or parsed > max_value:
        raise ReservationValidationError(f"{field_name} must be between 1 and {max_value}")
    return parsed


class SyntheticReservationStore:
    def __init__(
        self,
        storage_path: Path,
        ttl: timedelta,
        max_per_call: int = 3,
    ) -> None:
        self._storage_path = storage_path
        self._ttl = ttl
        self._max_per_call = max_per_call
        self._lock = threading.Lock()

    async def create_reservation(
        self,
        payload: dict[str, Any],
        *,
        session: Optional[CallSession] = None,
    ) -> CreateReservationResult:
        try:
            try:
                arrival_date = date.fromisoformat(str(payload.get("arrivalDate", "")))
            except ValueError as exc:
                raise ReservationValidationError("arrivalDate must be YYYY-MM-DD") from exc
            nights = _read_positive_int(payload.get("nights"), "nights", max_value=60)
            guests = _read_positive_int(payload.get("guests"), "guests", max_value=30)
            today = date.today()
            if arrival_date < today or arrival_date > today + timedelta(days=365):
                raise ReservationValidationError(
                    "arrivalDate must be between today and 365 days from today"
                )
        except ReservationValidationError as exc:
            return CreateReservationResult(
                status="invalid_request",
                source="synthetic_reservation_store",
                demo_reservation=True,
                reservation=None,
                message_for_assistant=str(exc),
                error_code="invalid_reservation_request",
            )

        unit_id = str(payload.get("unitId", "")).strip()
        unit = unit_registry.find_unit(unit_id) if unit_id else None
        if unit is None:
            return CreateReservationResult(
                status="unit_not_found",
                source="synthetic_reservation_store",
                demo_reservation=True,
                reservation=None,
                message_for_assistant=(
                    "En löytänyt pyydettyä kohdetta demo-varausjärjestelmästä."
                ),
                error_code="unit_not_found",
            )

        departure_date = arrival_date + timedelta(days=nights)
        arrival_iso = arrival_date.isoformat()
        departure_iso = departure_date.isoformat()

        history: Optional[list[dict[str, Any]]] = None
        if session is not None:
            history = session.metadata.setdefault("create_reservation_history", [])
            for entry in history:
                if (
                    entry.get("unit_id") == unit.unit_id
                    and entry.get("arrival_date") == arrival_iso
                    and entry.get("departure_date") == departure_iso
                ):
                    existing_reservation = self._find_reservation_by_id(
                        entry.get("reservation_id")
                    )
                    return CreateReservationResult(
                        status="already_reserved_for_stay",
                        source="synthetic_reservation_store",
                        demo_reservation=True,
                        reservation=existing_reservation,
                        message_for_assistant=(
                            "Tämä yöpyminen on jo varattu tämän puhelun aikana "
                            "demo-varausjärjestelmässä."
                        ),
                        error_code="already_reserved_for_stay",
                    )

            if len(history) >= self._max_per_call:
                return CreateReservationResult(
                    status="already_reserved_for_stay",
                    source="synthetic_reservation_store",
                    demo_reservation=True,
                    reservation=None,
                    message_for_assistant=(
                        "Tällä puhelulla ei voi enää tehdä uusia demo-varauksia."
                    ),
                    error_code="reservation_cap_reached",
                )

        with self._lock:
            now = datetime.now(timezone.utc)
            state = self._read_state_unlocked()
            active_reservations = self._active_reservations_unlocked(state, now=now)

            if guests > unit.capacity:
                return CreateReservationResult(
                    status="unavailable",
                    source="synthetic_reservation_store",
                    demo_reservation=True,
                    reservation=None,
                    message_for_assistant=(
                        f"Kohteeseen {unit.display_name} mahtuu enintään {unit.capacity} henkilöä."
                    ),
                    error_code="capacity_exceeded",
                )

            if nights < unit.min_nights:
                return CreateReservationResult(
                    status="unavailable",
                    source="synthetic_reservation_store",
                    demo_reservation=True,
                    reservation=None,
                    message_for_assistant=(
                        f"Kohteen {unit.display_name} minimivarausaika on {unit.min_nights} yötä."
                    ),
                    error_code="min_nights_not_met",
                )

            for record in active_reservations:
                if record["unit_id"] != unit.unit_id:
                    continue
                if self._stay_overlaps(
                    record,
                    arrival=arrival_date,
                    departure=departure_date,
                ):
                    return CreateReservationResult(
                        status="unavailable",
                        source="synthetic_reservation_store",
                        demo_reservation=True,
                        reservation=None,
                        message_for_assistant=(
                            f"Kohde {unit.display_name} ei ole vapaana valituille "
                            "päiville demo-varausjärjestelmässä."
                        ),
                        error_code="stay_overlap",
                    )

            created_at = _utc_now_iso()
            expires_at = (now + self._ttl).isoformat()
            reservation = Reservation(
                reservation_id=uuid.uuid4().hex[:8].upper(),
                unit_id=unit.unit_id,
                unit_name=unit.display_name,
                area=unit.area,
                arrival_date=arrival_iso,
                departure_date=departure_iso,
                nights=nights,
                guests=guests,
                price_total=nights * unit.nightly_rate_eur,
                currency="EUR",
                created_at=created_at,
                expires_at=expires_at,
            )

            pruned_reservations = [
                record
                for record in state.get("reservations", [])
                if self._is_active(record, now=now)
            ]
            pruned_reservations.append(asdict(reservation))
            state["reservations"] = pruned_reservations
            self._write_state_unlocked(state)

        if session is not None and history is not None:
            history.append(
                {
                    "reservation_id": reservation.reservation_id,
                    "unit_id": reservation.unit_id,
                    "arrival_date": reservation.arrival_date,
                    "departure_date": reservation.departure_date,
                    "created_at": reservation.created_at,
                }
            )

        return CreateReservationResult(
            status="confirmed",
            source="synthetic_reservation_store",
            demo_reservation=True,
            reservation=reservation,
            message_for_assistant=(
                f"Varaus kohteeseen {unit.display_name} on tehty Hotelli Framin "
                f"demonstraatiovarausjärjestelmään. Tämä ei ole oikea, sitova varaus. "
                f"Varausviite: {reservation.reservation_id}."
            ),
            error_code=None,
        )

    def list_active_reservations(self) -> list[Reservation]:
        with self._lock:
            now = datetime.now(timezone.utc)
            state = self._read_state_unlocked()
            active_records = self._active_reservations_unlocked(state, now=now)
        return [Reservation(**record) for record in active_records]

    def _find_reservation_by_id(self, reservation_id: Optional[str]) -> Optional[Reservation]:
        if not reservation_id:
            return None
        # Best-effort lookup only, used to echo an already-created reservation back
        # in a duplicate-dispatch result; not part of the create/write critical section.
        state = self._read_state_unlocked()
        for record in state.get("reservations", []):
            if record.get("reservation_id") == reservation_id:
                return Reservation(**record)
        return None

    def _read_state_unlocked(self) -> dict[str, Any]:
        if not self._storage_path.exists():
            return {"reservations": []}

        try:
            payload = json.loads(self._storage_path.read_text(encoding="utf-8"))
        except (OSError, JSONDecodeError) as exc:
            logger.warning("Failed to read reservation store at %s: %s", self._storage_path, exc)
            return {"reservations": []}

        reservations = payload.get("reservations")
        if not isinstance(reservations, list):
            logger.warning(
                "Reservation store at %s is missing a valid reservations list",
                self._storage_path,
            )
            return {"reservations": []}

        return {"reservations": reservations}

    def _write_state_unlocked(self, state: dict[str, Any]) -> None:
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._storage_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _is_active(reservation: dict[str, Any], *, now: datetime) -> bool:
        expires_at_raw = reservation.get("expires_at")
        if not expires_at_raw:
            logger.warning("Reservation record missing expires_at; treating as expired: %s", reservation)
            return False
        try:
            expires_at = datetime.fromisoformat(expires_at_raw)
        except ValueError:
            logger.warning(
                "Reservation record has unparseable expires_at=%s; treating as expired",
                expires_at_raw,
            )
            return False
        return now < expires_at

    @classmethod
    def _active_reservations_unlocked(
        cls, state: dict[str, Any], *, now: datetime
    ) -> list[dict[str, Any]]:
        return [
            record for record in state.get("reservations", []) if cls._is_active(record, now=now)
        ]

    @staticmethod
    def _stay_overlaps(
        existing: dict[str, Any],
        *,
        arrival: date,
        departure: date,
    ) -> bool:
        existing_arrival = date.fromisoformat(existing["arrival_date"])
        existing_departure = date.fromisoformat(existing["departure_date"])
        return arrival < existing_departure and existing_arrival < departure
