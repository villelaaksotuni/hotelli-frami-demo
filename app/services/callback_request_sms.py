from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from app.config.settings import settings
from app.models.call import CallSession, utc_now_iso
from app.services.sms_utils import extract_counterparty_phone, normalize_phone


class SmsDestinationError(RuntimeError):
    """Raised when the SMS send destination is not the server-configured owner phone."""


@dataclass(frozen=True)
class CallbackRequestSmsResult:
    sent: bool
    skipped_reason: Optional[str]
    message_for_assistant: str
    error_code: Optional[str] = None
    caller_phone: Optional[str] = None
    owner_phone: Optional[str] = None
    caller_name: Optional[str] = None
    reason: Optional[str] = None
    message_sid: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "sent" if self.sent else "not_sent",
            "sent": self.sent,
            "booking_not_confirmed": True,
            "skipped_reason": self.skipped_reason,
            "message_for_assistant": self.message_for_assistant,
            "error_code": self.error_code,
            "caller_phone": self.caller_phone,
            "owner_phone": self.owner_phone,
            "caller_name": self.caller_name,
            "reason": self.reason,
            "message_sid": self.message_sid,
        }


class CallbackRequestSmsService:
    def __init__(
        self,
        *,
        from_phone: Optional[str],
        owner_phone: Optional[str],
        twilio_client: Any,
    ) -> None:
        self._from_phone = from_phone
        self._owner_phone = normalize_phone(owner_phone)
        self._twilio_client = twilio_client

    def send_callback_request(
        self,
        *,
        session: Optional[CallSession],
        caller_name: Optional[str],
        reason: Optional[str],
    ) -> CallbackRequestSmsResult:
        if session is None:
            return CallbackRequestSmsResult(
                sent=False,
                skipped_reason="missing_session",
                error_code="missing_session",
                message_for_assistant=(
                    "En voi lähettää yhteydenottopyyntöä, koska aktiivista puhelusessiota ei löytynyt."
                ),
            )

        caller_phone = extract_counterparty_phone(session.metadata)
        if not caller_phone:
            return CallbackRequestSmsResult(
                sent=False,
                skipped_reason="missing_caller_phone",
                error_code="missing_caller_phone",
                message_for_assistant=(
                    "En voi lähettää yhteydenottopyyntöä, koska soittajan puhelinnumero ei ole saatavilla."
                ),
            )

        if not self._owner_phone:
            return CallbackRequestSmsResult(
                sent=False,
                skipped_reason="owner_phone_not_configured",
                error_code="owner_phone_not_configured",
                caller_phone=caller_phone,
                message_for_assistant=(
                    "En voi lähettää yhteydenottopyyntöä juuri nyt, koska vastaanoton numeroa ei ole asetettu."
                ),
            )

        if self._twilio_client is None or not self._from_phone:
            return CallbackRequestSmsResult(
                sent=False,
                skipped_reason="twilio_not_configured",
                error_code="twilio_not_configured",
                caller_phone=caller_phone,
                owner_phone=self._owner_phone,
                message_for_assistant=(
                    "En voi lähettää yhteydenottopyyntöä juuri nyt, koska tekstiviestiasetukset puuttuvat."
                ),
            )

        cleaned_name = _clean_optional_text(caller_name, max_length=80)
        cleaned_reason = _clean_optional_text(reason, max_length=280)

        history = session.metadata.setdefault("callback_request_sms_history", [])
        if history:
            return CallbackRequestSmsResult(
                sent=False,
                skipped_reason="already_sent_for_session",
                error_code="already_sent_for_session",
                caller_phone=caller_phone,
                owner_phone=self._owner_phone,
                caller_name=cleaned_name,
                reason=cleaned_reason,
                message_for_assistant=(
                    "Yhteydenottopyyntö on jo lähetetty tämän puhelun aikana."
                ),
            )

        destination = self._owner_phone
        if not destination:
            raise SmsDestinationError(
                "SMS destination is empty; the SMS destination is the server-configured "
                "reception number and never a caller-supplied or tool-supplied value."
            )
        if destination != normalize_phone(destination):
            raise SmsDestinationError(
                "SMS destination is not normalized; the SMS destination is the "
                "server-configured reception number and never a caller-supplied or "
                "tool-supplied value."
            )
        if destination == caller_phone:
            raise SmsDestinationError(
                "SMS destination equals the caller's own number; the SMS destination is "
                "the server-configured reception number and never a caller-supplied or "
                "tool-supplied value."
            )

        message = self._twilio_client.messages.create(
            body=self._build_sms_body(
                caller_phone=caller_phone,
                caller_name=cleaned_name,
                reason=cleaned_reason,
            ),
            from_=self._from_phone,
            to=destination,
        )
        message_sid = getattr(message, "sid", None)
        history.append(
            {
                "sent_at": utc_now_iso(),
                "caller_phone": caller_phone,
                "owner_phone": self._owner_phone,
                "caller_name": cleaned_name,
                "reason": cleaned_reason,
                "message_sid": message_sid,
            }
        )

        return CallbackRequestSmsResult(
            sent=True,
            skipped_reason=None,
            caller_phone=caller_phone,
            owner_phone=self._owner_phone,
            caller_name=cleaned_name,
            reason=cleaned_reason,
            message_sid=message_sid,
            message_for_assistant=(
                "Lähetin vastaanottoon tekstiviestillä yhteydenottopyynnön."
            ),
        )

    @staticmethod
    def _build_sms_body(
        *,
        caller_phone: str,
        caller_name: Optional[str],
        reason: Optional[str],
    ) -> str:
        parts = [
            "Hotelli Frami: vastaanottoon soittopyyntö.",
            f"Soittajan numero: {caller_phone}.",
        ]
        if caller_name:
            parts.append(f"Nimi: {caller_name}.")
        if reason:
            parts.append(f"Syy: {reason}.")
        else:
            parts.append("Syy: Asiakas pyysi, että hotellin henkilökunta ottaa yhteyttä.")
        return " ".join(parts)


def _clean_optional_text(value: Optional[str], *, max_length: int) -> Optional[str]:
    cleaned = " ".join(str(value or "").split()).strip()
    if not cleaned:
        return None
    return cleaned[:max_length]


callback_request_sms_service = CallbackRequestSmsService(
    from_phone=settings.twilio_phone_number,
    owner_phone=settings.callback_request_to_phone,
    twilio_client=settings.twilio_client,
)
