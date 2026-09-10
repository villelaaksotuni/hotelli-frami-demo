# BookingOnline Availability Checker

The availability checker lives in:

- `app/services/availability_registry.py` for configured BookingOnline products
- `app/services/bookingonline_fetcher.py` for HTTP calendar loading
- `app/services/bookingonline_parser.py` for HTML parsing
- `app/services/availability_checker.py` for validation, interpretation, and assistant-safe response shaping
- `app/routes/availability.py` for REST endpoints

## Endpoints

- `GET /api/bookingonline/units` lists configured units.
- `POST /api/bookingonline/availability` checks availability.

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

`area` and `unitId` are optional. `unitId` takes priority over `area`.

## Updating Units

Add or edit units in `BOOKINGONLINE_UNITS` in `app/services/availability_registry.py`.
Keep `unitId` stable because callers, logs, or prompts may refer to it. For Hotelli Frami,
`teemaId` and `myyjaId` are currently shared defaults, while each unit has its own
`kiinteaTuoteId`. The customer booking product id is generated as `{myyjaId}-{kiinteaTuoteId}`.

The checker never confirms a booking or takes payment. It returns `booking_not_confirmed: true`
and, when available, a BookingOnline URL where the customer can complete the booking.
