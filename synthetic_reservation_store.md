# Synthetic Reservation Store

The synthetic booking backend lives in:

- `app/models/reservation.py` for the vendor-neutral data contract (units, availability,
  reservations)
- `app/services/unit_registry.py` for the static, in-code unit table and the fuzzy
  name/area matcher
- `app/services/synthetic_reservation_store.py` for the concrete backend: validation,
  availability computation, and reservation creation/persistence
- `app/services/reservation_provider.py` — the single seam every caller (voice tool and
  HTTP route) goes through
- `app/routes/availability.py` for the public HTTP endpoints

This subsystem replaces the former HTML-scraping BookingOnline integration entirely. It is
synthetic, self-contained, and isolated: no code path in this subsystem opens a network
socket or reaches any live production booking system.

## HTTP Endpoints

- `GET /api/reservations/units` lists the static unit registry.
- `POST /api/reservations/availability` checks in-process availability for a stay.

Request body:

```json
{
  "arrivalDate": "2026-05-16",
  "nights": 8,
  "guests": 4,
  "area": "Jokipuisto",
  "unitId": "jokipuistopark-asunto-2"
}
```

`area`, `unitName` and `unitId` are optional. `unitId` takes priority, then `unitName`
(resolved through the fuzzy matcher), then `area`.

Response shape (`AvailabilityResponse.to_dict()`):

```json
{
  "status": "available",
  "confidence": "high",
  "scraped_at": "2026-05-01T12:00:00+00:00",
  "source": "synthetic_reservation_store",
  "query": { "...": "..." },
  "options": [
    {
      "unit_id": "jokipuistopark-asunto-2",
      "name": "Jokipuistopark asunto 2",
      "area": "Jokipuisto",
      "status": "available",
      "price_total": 1104,
      "currency": "EUR",
      "available_durations": [],
      "reason": "..."
    }
  ],
  "booking_not_confirmed": true,
  "message_for_assistant": "...",
  "error_code": null
}
```

## Realtime Tools

Two Realtime tools reach this subsystem, both declared in `app/services/realtime_session.py`
and dispatched in `app/services/realtime_tools.py` through `reservation_provider` only:

- `check_availability` — required parameters `arrivalDate`, `nights`, `guests`; optional
  `area`, `unitName`, `unitId`. Never creates or confirms a reservation.
- `create_reservation` — required parameters `arrivalDate`, `nights`, `guests`, `unitId`;
  optional `unitName` fallback. Creates a demo reservation record.

## Availability Status Ladder

`AvailabilityOption.status` is one of:

- `available` — the unit is free for the requested stay; `price_total` and `currency`
  are populated.
- `unavailable` — an active (non-expired) reservation for that unit overlaps the
  requested stay.
- `not_selectable` — the arrival date is before today or more than 365 days ahead.
- `guest_count_unavailable` — the requested `guests` exceeds the unit's `capacity`.
- `duration_unavailable` — the requested `nights` is below the unit's `min_nights`;
  `available_durations` lists stay lengths that are genuinely free and priced.
- `unknown` — the store could not be read reliably (never a signal to retry against a
  remote source — there is no remote source).

## Persistence Model

- A single JSON file under `APP_DATA_DIR`, guarded by a `threading.Lock`.
- Reads are corruption-tolerant: a missing file, unreadable JSON, or a malformed
  `reservations` list all degrade to an empty in-memory state rather than raising.
- Writes prune expired reservations first (prune-on-write), so the file never grows
  unbounded with stale records.
- Reservation TTL expiry is lazy and exclusive at the boundary: a reservation is
  considered active only while `now < expires_at`.
- Reservation records carry no caller-identifying fields (no phone number, no caller
  name, no transcript reference) by design, so a future public board (Phase 3, BOARD-01)
  can render active reservations directly.

## Settings

| Environment variable | Default | Purpose |
|---|---|---|
| `SYNTHETIC_RESERVATION_STORE_PATH` | `{APP_DATA_DIR}/reservations.json` | Where the JSON reservation file is stored. |
| `SYNTHETIC_RESERVATION_TTL_HOURS` | `24.0` | How long a created reservation blocks the same unit/stay before lazily expiring. |
| `SYNTHETIC_MAX_RESERVATIONS_PER_CALL` | `3` | Hard cap on reservations created within a single call (denial-of-demo mitigation). |

## Swapping the Backend

`reservation_provider.py` is the only module that imports the concrete
`SyntheticReservationStore` class. Every consumer — the Realtime tool dispatcher and the
HTTP routes — imports `reservation_provider` (and `ReservationValidationError`) from that
module and nothing else. Swapping the backend for a different implementation means
editing the singleton construction line in `reservation_provider.py` alone; no other file
in `app/` needs to change.

## Updating Units

Add or edit units in `UNITS` in `app/services/unit_registry.py`. Keep `unit_id` stable
because callers, logs, or prompts may refer to it. Each unit carries `capacity`,
`nightly_rate_eur`, and `min_nights`, which the store uses directly to compute pricing
and the availability status ladder above.

The store never confirms a real, binding booking or takes payment. Every response and
every created reservation is marked as a demonstration record (`booking_not_confirmed`
on availability responses, `demo_reservation` on reservation results).
