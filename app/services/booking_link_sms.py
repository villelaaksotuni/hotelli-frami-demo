from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from app.config.settings import settings
from app.models.call import CallSession, utc_now_iso
from app.services.availability_registry import find_unit, find_unit_by_tuote_id
from app.services.sms_utils import extract_counterparty_phone, extract_live_call_origin_phone

ENGLISH_LANGUAGE_MARKERS = (
    " hello ",
    " hi ",
    " thank ",
    " thanks ",
    " please ",
    " booking ",
    " room ",
    " can you ",
    " i need ",
)

FINNISH_LANGUAGE_MARKERS = (
    " hei ",
    " moi ",
    " kiitos ",
    " varaus ",
    " huone ",
    " voinko ",
    " tarvitsen ",
    " miten ",
)


@dataclass(frozen=True)
class BookingLinkSmsResult:
    sent: bool
    skipped_reason: Optional[str]
    message_for_assistant: str
    error_code: Optional[str] = None
    to_phone: Optional[str] = None
    unit_id: Optional[str] = None
    tuote_id: Optional[str] = None
    calendar_url: Optional[str] = None
    message_sid: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "sent" if self.sent else "not_sent",
            "sent": self.sent,
            "booking_not_confirmed": True,
            "skipped_reason": self.skipped_reason,
            "message_for_assistant": self.message_for_assistant,
            "error_code": self.error_code,
            "to_phone": self.to_phone,
            "unit_id": self.unit_id,
            "tuote_id": self.tuote_id,
            "calendar_url": self.calendar_url,
            "message_sid": self.message_sid,
        }


class BookingLinkSmsService:
    def __init__(
        self,
        *,
        from_phone: Optional[str],
        twilio_client: Any,
    ) -> None:
        self._from_phone = from_phone
        self._twilio_client = twilio_client

    def send_calendar_link(
        self,
        *,
        session: Optional[CallSession],
        tuote_id: Optional[str],
        unit_id: Optional[str],
    ) -> BookingLinkSmsResult:
        if session is None:
            return BookingLinkSmsResult(
                sent=False,
                skipped_reason="missing_session",
                error_code="missing_session",
                message_for_assistant=(
                    "En voi lähettää tekstiviestiä, koska aktiivista puhelusessiota ei löytynyt."
                ),
            )

        phone = extract_live_call_origin_phone(session.metadata) or extract_counterparty_phone(
            session.metadata
        )
        if not phone:
            return BookingLinkSmsResult(
                sent=False,
                skipped_reason="missing_phone",
                error_code="missing_phone",
                message_for_assistant=(
                    "En voi lähettää tekstiviestiä, koska soittajan puhelinnumero ei ole saatavilla."
                ),
            )

        if self._twilio_client is None or not self._from_phone:
            return BookingLinkSmsResult(
                sent=False,
                skipped_reason="twilio_not_configured",
                error_code="twilio_not_configured",
                to_phone=phone,
                message_for_assistant=(
                    "En voi lähettää tekstiviestiä juuri nyt, koska tekstiviestiasetukset puuttuvat."
                ),
            )

        unit = self._resolve_unit(tuote_id=tuote_id, unit_id=unit_id)
        if unit is None:
            return BookingLinkSmsResult(
                sent=False,
                skipped_reason="unit_not_found",
                error_code="unit_not_found",
                to_phone=phone,
                unit_id=unit_id,
                tuote_id=tuote_id,
                message_for_assistant=(
                    "En löytänyt pyydettyä varauskalenteria tekstiviestin lähettämistä varten."
                ),
            )

        if not unit.calendarUrl:
            return BookingLinkSmsResult(
                sent=False,
                skipped_reason="calendar_url_missing",
                error_code="calendar_url_missing",
                to_phone=phone,
                unit_id=unit.unitId,
                tuote_id=unit.tuoteId,
                message_for_assistant=(
                    "En löytänyt tälle kohteelle lähetettävää varauskalenterilinkkiä."
                ),
            )

        history = session.metadata.setdefault("booking_link_sms_history", [])
        if any(item.get("tuote_id") == unit.tuoteId for item in history if isinstance(item, dict)):
            return BookingLinkSmsResult(
                sent=False,
                skipped_reason="already_sent_for_unit",
                error_code="already_sent_for_unit",
                to_phone=phone,
                unit_id=unit.unitId,
                tuote_id=unit.tuoteId,
                calendar_url=unit.calendarUrl,
                message_for_assistant=(
                    f"Varauskalenterilinkki kohteeseen {unit.displayName} on jo lähetetty tämän puhelun aikana."
                ),
            )

        language = self._resolve_message_language(session)
        message = self._twilio_client.messages.create(
            body=self._build_sms_body(unit.displayName, unit.calendarUrl, language=language),
            from_=self._from_phone,
            to=phone,
        )
        message_sid = getattr(message, "sid", None)
        history.append(
            {
                "sent_at": utc_now_iso(),
                "to_phone": phone,
                "unit_id": unit.unitId,
                "tuote_id": unit.tuoteId,
                "calendar_url": unit.calendarUrl,
                "message_sid": message_sid,
                "language": language,
            }
        )

        return BookingLinkSmsResult(
            sent=True,
            skipped_reason=None,
            to_phone=phone,
            unit_id=unit.unitId,
            tuote_id=unit.tuoteId,
            calendar_url=unit.calendarUrl,
            message_sid=message_sid,
            message_for_assistant=(
                f"Lähetin tekstiviestillä kohteen {unit.displayName} varauskalenterilinkin numeroon {phone}."
            ),
        )

    @staticmethod
    def _build_sms_body(display_name: str, calendar_url: str, *, language: str) -> str:
        if language == "en":
            return f"Hotelli Frami: Here is the booking calendar for {display_name}: {calendar_url}"
        return f"Hotelli Frami: Tässä varauskalenteri kohteeseen {display_name}: {calendar_url}"

    @classmethod
    def _resolve_message_language(cls, session: CallSession) -> str:
        combined_text = " ".join(
            str(turn.get("text") or "")
            for turn in session.merged_dialogue_turns()
            if isinstance(turn, dict)
        ).casefold()
        if combined_text:
            padded = f" {re.sub(r'\\s+', ' ', combined_text).strip()} "
            english_score = sum(marker in padded for marker in ENGLISH_LANGUAGE_MARKERS)
            finnish_score = sum(marker in padded for marker in FINNISH_LANGUAGE_MARKERS)
            if english_score > finnish_score and english_score >= 1:
                return "en"
            if finnish_score > english_score and finnish_score >= 1:
                return "fi"

        normalized_language = str(session.config.language or settings.default_language).strip().lower()
        if normalized_language.startswith("en"):
            return "en"
        return "fi"

    @staticmethod
    def _resolve_unit(*, tuote_id: Optional[str], unit_id: Optional[str]):
        normalized_tuote_id = str(tuote_id or "").strip()
        if normalized_tuote_id:
            unit = find_unit_by_tuote_id(normalized_tuote_id)
            if unit is not None:
                return unit

        normalized_unit_id = str(unit_id or "").strip()
        if normalized_unit_id:
            return find_unit(normalized_unit_id)

        return None


booking_link_sms_service = BookingLinkSmsService(
    from_phone=settings.twilio_phone_number,
    twilio_client=settings.twilio_client,
)
