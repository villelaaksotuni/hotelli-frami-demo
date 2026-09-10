import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.services.availability_checker import (
    AvailabilityValidationError,
    availability_checker,
)
from app.services.availability_registry import get_all_units

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/api/bookingonline/units")
async def list_bookingonline_units():
    return JSONResponse(content={"items": [unit.to_dict() for unit in get_all_units()]})


@router.post("/api/bookingonline/availability")
async def check_bookingonline_availability(request: Request):
    try:
        payload = await request.json()
        result = await availability_checker.check(payload)
        return JSONResponse(content=result.to_dict())
    except AvailabilityValidationError as exc:
        return JSONResponse(
            status_code=400,
            content={
                "status": "unknown",
                "booking_not_confirmed": True,
                "error_code": "invalid_availability_query",
                "message_for_assistant": str(exc),
            },
        )
    except Exception as exc:
        logger.exception("Unhandled availability endpoint error: %s", exc)
        return JSONResponse(
            status_code=500,
            content={
                "status": "unknown",
                "booking_not_confirmed": True,
                "error_code": "availability_check_failed",
                "message_for_assistant": "Availability could not be checked reliably.",
            },
        )
