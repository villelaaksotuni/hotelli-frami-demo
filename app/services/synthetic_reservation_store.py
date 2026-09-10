from __future__ import annotations

import json
import logging
import threading
import uuid
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Iterable, Optional

from app.models.call import CallSession, utc_now_iso
from app.models.reservation import (
    AvailabilityOption,
    AvailabilityQuery,
    AvailabilityResponse,
    AvailabilityStatus,
    AvailableDuration,
    CreateReservationResult,
    Reservation,
    ReservationValidationError,
    Unit,
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


def validate_availability_payload(payload: dict[str, Any]) -> AvailabilityQuery:
    try:
        arrival_date = date.fromisoformat(str(payload.get("arrivalDate", "")))
    except ValueError as exc:
        raise ReservationValidationError("arrivalDate must be YYYY-MM-DD") from exc

    nights = _read_positive_int(payload.get("nights"), "nights", max_value=60)
    guests = _read_positive_int(payload.get("guests"), "guests", max_value=30)
    area = unit_registry.normalize_area(payload.get("area"))
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
            f"Demo-varausjärjestelmässä näkyy saatavuutta kohteessa {first.name} "
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
        suffix = f" Vapaana olevat kestot ovat: {alternative_text} yötä." if alternative_text else ""
        return (
            f"Tulopäivä {query.arrival_date} on valittavissa, mutta {query.nights} yön "
            f"kestoa ei ole vapaana.{suffix} Varausta ei ole vahvistettu."
        )

    if status == "guest_count_unavailable":
        return (
            f"Pyydettyä henkilömäärää {query.guests} ei mahdu tarkistettuihin kohteisiin "
            "demo-varausjärjestelmässä. Varausta ei ole vahvistettu."
        )

    if status == "not_selectable":
        return (
            f"Tulopäivä {query.arrival_date} ei ole valittavissa demo-varausjärjestelmässä "
            "(liian lähellä tai liian kaukana nykyhetkestä)."
        )

    return (
        "En pysty tarkistamaan saatavuutta luotettavasti demo-varausjärjestelmästä juuri nyt. "
        "Älä lupaa saatavuutta tai hintaa vahvistettuna."
    )


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
                    with self._lock:
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

    async def check_availability(self, payload: dict[str, Any]) -> AvailabilityResponse:
        query = validate_availability_payload(payload)
        units = unit_registry.select_units(
            unit_id=query.unit_id, unit_name=query.unit_name, area=query.area
        )
        scraped_at = utc_now_iso()

        if not units:
            return AvailabilityResponse(
                status="unknown",
                confidence="low",
                scraped_at=scraped_at,
                source="synthetic_reservation_store",
                query=query,
                options=[],
                booking_not_confirmed=True,
                message_for_assistant=(
                    "En löytänyt pyydettyyn kohteeseen sopivaa demo-varausjärjestelmän kohdetta."
                ),
                error_code="unit_not_found",
            )

        with self._lock:
            now = datetime.now(timezone.utc)
            state = self._read_state_unlocked()
            active_reservations = self._active_reservations_unlocked(state, now=now)

        today = date.today()
        options = [
            self._availability_for_unit(unit, query, active_reservations, today=today)
            for unit in units
        ]
        status = _aggregate_status(option.status for option in options)
        return AvailabilityResponse(
            status=status,
            confidence=_confidence_for(status, options),
            scraped_at=scraped_at,
            source="synthetic_reservation_store",
            query=query,
            options=options,
            booking_not_confirmed=True,
            message_for_assistant=_build_assistant_message(status, query, options),
            error_code=None if status != "unknown" else "availability_uninterpretable",
        )

    def _availability_for_unit(
        self,
        unit: Unit,
        query: AvailabilityQuery,
        active_reservations: list[dict[str, Any]],
        *,
        today: date,
    ) -> AvailabilityOption:
        arrival_date = date.fromisoformat(query.arrival_date)
        departure_date = date.fromisoformat(query.departure_date)

        if arrival_date < today or arrival_date > today + timedelta(days=365):
            return AvailabilityOption(
                unit_id=unit.unit_id,
                name=unit.display_name,
                area=unit.area,
                status="not_selectable",
                reason=(
                    "Tulopäivä ei ole valittavissa demo-varausjärjestelmässä "
                    "(liian lähellä tai liian kaukana nykyhetkestä)."
                ),
            )

        if query.guests > unit.capacity:
            return AvailabilityOption(
                unit_id=unit.unit_id,
                name=unit.display_name,
                area=unit.area,
                status="guest_count_unavailable",
                reason=(
                    f"Kohteeseen {unit.display_name} mahtuu enintään {unit.capacity} henkilöä."
                ),
            )

        if query.nights < unit.min_nights:
            return AvailabilityOption(
                unit_id=unit.unit_id,
                name=unit.display_name,
                area=unit.area,
                status="duration_unavailable",
                available_durations=self._free_durations_for_unit(
                    unit, query, active_reservations
                ),
                reason=(
                    f"Kohteen {unit.display_name} minimivarausaika on {unit.min_nights} yötä."
                ),
            )

        for record in active_reservations:
            if record["unit_id"] != unit.unit_id:
                continue
            if self._stay_overlaps(record, arrival=arrival_date, departure=departure_date):
                return AvailabilityOption(
                    unit_id=unit.unit_id,
                    name=unit.display_name,
                    area=unit.area,
                    status="unavailable",
                    reason=(
                        f"Kohde {unit.display_name} on jo varattu demo-varausjärjestelmässä "
                        "valituille päiville."
                    ),
                )

        return AvailabilityOption(
            unit_id=unit.unit_id,
            name=unit.display_name,
            area=unit.area,
            status="available",
            price_total=query.nights * unit.nightly_rate_eur,
            currency="EUR",
            reason=(
                f"Kohde {unit.display_name} näkyy vapaana demo-varausjärjestelmässä "
                "pyydetylle ajanjaksolle."
            ),
        )

    @staticmethod
    def _free_durations_for_unit(
        unit: Unit,
        query: AvailabilityQuery,
        active_reservations: list[dict[str, Any]],
    ) -> list[AvailableDuration]:
        arrival_date = date.fromisoformat(query.arrival_date)
        candidates: list[AvailableDuration] = []
        nights = unit.min_nights
        while len(candidates) < 6:
            departure_date = arrival_date + timedelta(days=nights)
            overlaps = any(
                record["unit_id"] == unit.unit_id
                and SyntheticReservationStore._stay_overlaps(
                    record, arrival=arrival_date, departure=departure_date
                )
                for record in active_reservations
            )
            if not overlaps:
                price_total = nights * unit.nightly_rate_eur
                candidates.append(
                    AvailableDuration(
                        nights=nights,
                        price_total=price_total,
                        currency="EUR",
                        raw_label=f"{nights} yötä, {price_total} euroa",
                    )
                )
            nights += 1
            if nights > unit.min_nights + 30:
                break
        return candidates

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
        tmp_path = self._storage_path.with_name(self._storage_path.name + ".tmp")
        tmp_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp_path.replace(self._storage_path)

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
