from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Optional

from app.config.settings import settings
from app.models.call import ConversationLog

logger = logging.getLogger(__name__)

RATING_PATTERN = re.compile(r"\b(10|[1-9])\b")
RATING_ONLY_PATTERN = re.compile(r"^\s*(10|[1-9])\s*$")

DEFAULT_FEEDBACK_MESSAGE_FI = (
    "Kiitos soitostasi Hotelli Framin tekoälyavustajalle. "
    "Kuinka hyvin pystyimme auttamaan sinua? "
    "Vastaa numerolla 1-10, missä 10 = erittäin hyvin. "
    "Voit halutessasi kirjoittaa myös vapaamuotoisen palautteen."
)

DEFAULT_FEEDBACK_MESSAGE_EN = (
    "Thanks for calling Hotelli Frami's AI assistant. "
    "How well were we able to help you? "
    "Reply with a number from 1 to 10, where 10 = extremely well. "
    "You can also send free-form feedback."
)


@dataclass(frozen=True)
class FeedbackInviteResult:
    sent: bool
    skipped_reason: Optional[str]
    to_phone: Optional[str] = None
    message_sid: Optional[str] = None


@dataclass(frozen=True)
class FeedbackResponseResult:
    accepted: bool
    skipped_reason: Optional[str]
    normalized_phone: Optional[str] = None
    rating: Optional[int] = None
    reply_message: str = ""


class FeedbackSurveyService:
    def __init__(
        self,
        *,
        history_path: Path,
        enabled: bool,
        survey_message: str,
        from_phone: Optional[str],
        twilio_client: Any,
    ) -> None:
        self._history_path = history_path
        self._enabled = enabled
        self._survey_message = survey_message
        self._from_phone = from_phone
        self._twilio_client = twilio_client

    def send_invite_if_needed(
        self,
        *,
        metadata: dict[str, Any],
        call_sid: Optional[str],
        stream_sid: Optional[str],
        language: Optional[str],
        dialogue_turns: ConversationLog,
    ) -> FeedbackInviteResult:
        if not self._enabled:
            return FeedbackInviteResult(sent=False, skipped_reason="disabled")

        phone = self._extract_counterparty_phone(metadata)
        if not phone:
            return FeedbackInviteResult(sent=False, skipped_reason="missing_phone")

        if not self._has_user_turn(dialogue_turns):
            return FeedbackInviteResult(sent=False, skipped_reason="no_user_turns")

        if self._twilio_client is None or not self._from_phone:
            return FeedbackInviteResult(sent=False, skipped_reason="twilio_not_configured")

        history = self._read_history()
        if phone in history.get("invites_by_phone", {}):
            return FeedbackInviteResult(
                sent=False,
                skipped_reason="already_invited",
                to_phone=phone,
            )

        resolved_language = self._detect_conversation_language(
            dialogue_turns=dialogue_turns,
            fallback_language=language,
        )
        survey_message = self._build_survey_message(resolved_language)
        message = self._twilio_client.messages.create(
            body=survey_message,
            from_=self._from_phone,
            to=phone,
        )
        message_sid = getattr(message, "sid", None)
        invite_record = {
            "phone": phone,
            "invited_at": self._utc_now_iso(),
            "message_sid": message_sid,
            "call_sid": call_sid,
            "stream_sid": stream_sid,
            "language": resolved_language,
            "survey_message": survey_message,
        }
        history.setdefault("invites_by_phone", {})[phone] = invite_record
        history.setdefault("responses", [])
        self._write_history(history)
        return FeedbackInviteResult(
            sent=True,
            skipped_reason=None,
            to_phone=phone,
            message_sid=message_sid,
        )

    def record_response(
        self,
        *,
        from_phone: str,
        body: str,
        message_sid: Optional[str],
    ) -> FeedbackResponseResult:
        if not self._enabled:
            return FeedbackResponseResult(
                accepted=False,
                skipped_reason="disabled",
                reply_message="Palautekysely ei ole tällä hetkellä käytössä.",
            )

        normalized_phone = self._normalize_phone(from_phone)
        if not normalized_phone:
            return FeedbackResponseResult(
                accepted=False,
                skipped_reason="invalid_phone",
                reply_message="Palautteen käsittely ei onnistunut.",
            )

        history = self._read_history()
        invite_record = history.get("invites_by_phone", {}).get(normalized_phone)
        if invite_record is None:
            return FeedbackResponseResult(
                accepted=False,
                skipped_reason="no_invite_found",
                normalized_phone=normalized_phone,
                reply_message=(
                    "Kiitos viestistä. Palaute tallennetaan vain lähetettyyn kyselyyn vastattaessa."
                ),
            )

        invite_language = self._normalize_language(invite_record.get("language"))
        cleaned_body = str(body or "").strip()
        if not cleaned_body:
            return FeedbackResponseResult(
                accepted=False,
                skipped_reason="empty_feedback",
                normalized_phone=normalized_phone,
                reply_message=self._reply_text(
                    "request_rating_or_feedback",
                    invite_language,
                ),
            )

        rating = self._extract_rating(cleaned_body)
        freeform_feedback = self._extract_freeform_feedback(cleaned_body)
        response_record = {
            "phone": normalized_phone,
            "rating": rating,
            "received_at": self._utc_now_iso(),
            "message_sid": message_sid,
            "raw_body": cleaned_body,
            "freeform_feedback": freeform_feedback,
            "invite_message_sid": invite_record.get("message_sid"),
            "call_sid": invite_record.get("call_sid"),
            "stream_sid": invite_record.get("stream_sid"),
            "language": invite_language,
        }
        history.setdefault("responses", []).append(response_record)
        invite_record["last_rating"] = rating
        invite_record["last_freeform_feedback"] = freeform_feedback
        invite_record["last_response_at"] = response_record["received_at"]
        invite_record["response_count"] = int(invite_record.get("response_count") or 0) + 1
        self._write_history(history)
        return FeedbackResponseResult(
            accepted=True,
            skipped_reason=None,
            normalized_phone=normalized_phone,
            rating=rating,
            reply_message=self._reply_text("thanks", invite_language),
        )

    def _extract_counterparty_phone(self, metadata: dict[str, Any]) -> Optional[str]:
        direction = str(metadata.get("direction") or "").strip().lower()
        if direction == "outbound":
            return self._normalize_phone(metadata.get("to_number"))
        if direction == "inbound":
            return self._normalize_phone(metadata.get("from_number"))
        return self._normalize_phone(metadata.get("to_number") or metadata.get("from_number"))

    @staticmethod
    def _has_user_turn(dialogue_turns: ConversationLog) -> bool:
        return any(
            str(turn.get("speaker") or "").strip().lower() == "user"
            and str(turn.get("text") or "").strip()
            for turn in dialogue_turns
        )

    @staticmethod
    def _normalize_phone(value: Any) -> Optional[str]:
        raw = str(value or "").strip()
        if not raw:
            return None
        if raw.startswith("+"):
            digits = "+" + "".join(ch for ch in raw[1:] if ch.isdigit())
        else:
            digits = "".join(ch for ch in raw if ch.isdigit())
        return digits if len(digits.replace("+", "")) >= 7 else None

    @staticmethod
    def _extract_rating(body: str) -> Optional[int]:
        match = RATING_PATTERN.search(body or "")
        if not match:
            return None
        value = int(match.group(1))
        return value if 1 <= value <= 10 else None

    @staticmethod
    def _extract_freeform_feedback(body: str) -> Optional[str]:
        cleaned = " ".join(str(body or "").split()).strip()
        if not cleaned:
            return None
        if RATING_ONLY_PATTERN.fullmatch(cleaned):
            return None
        return cleaned

    def _build_survey_message(self, language: Optional[str]) -> str:
        normalized = self._normalize_language(language)
        if normalized == "en":
            return DEFAULT_FEEDBACK_MESSAGE_EN

        base_message = self._survey_message.strip() or DEFAULT_FEEDBACK_MESSAGE_FI
        if "vapaamuoto" not in base_message.casefold():
            base_message = (
                f"{base_message} Voit halutessasi kirjoittaa myös vapaamuotoisen palautteen."
            )
        return base_message

    @staticmethod
    def _reply_text(kind: str, language: Optional[str]) -> str:
        normalized = FeedbackSurveyService._normalize_language(language)
        if normalized == "en":
            english_messages = {
                "thanks": "Thanks for your feedback.",
                "request_rating_or_feedback": (
                    "Thanks for your message. Reply with a number from 1 to 10 "
                    "or send free-form feedback."
                ),
            }
            return english_messages[kind]

        finnish_messages = {
            "thanks": "Kiitos palautteestasi.",
            "request_rating_or_feedback": (
                "Kiitos viestistä. Vastaa numerolla 1-10 tai kirjoita vapaamuotoinen palaute."
            ),
        }
        return finnish_messages[kind]

    @staticmethod
    def _normalize_language(language: Any) -> str:
        normalized = str(language or "").strip().lower()
        if normalized.startswith("fi"):
            return "fi"
        if normalized.startswith("en"):
            return "en"
        return "fi"

    @classmethod
    def _detect_conversation_language(
        cls,
        *,
        dialogue_turns: ConversationLog,
        fallback_language: Optional[str],
    ) -> str:
        combined_text = " ".join(
            str(turn.get("text") or "")
            for turn in dialogue_turns
            if isinstance(turn, dict)
        ).casefold()
        if not combined_text:
            return cls._normalize_language(fallback_language)

        english_markers = (
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
        finnish_markers = (
            " hei ",
            " moi ",
            " kiitos ",
            " varaus ",
            " huone ",
            " voinko ",
            " tarvitsen ",
            " miten ",
        )
        padded = f" {combined_text} "
        english_score = sum(marker in padded for marker in english_markers)
        finnish_score = sum(marker in padded for marker in finnish_markers)
        if english_score > finnish_score and english_score >= 1:
            return "en"
        if finnish_score > english_score and finnish_score >= 1:
            return "fi"
        return cls._normalize_language(fallback_language)

    def _read_history(self) -> dict[str, Any]:
        if not self._history_path.exists():
            return {"invites_by_phone": {}, "responses": []}
        try:
            payload = json.loads(self._history_path.read_text(encoding="utf-8"))
        except (OSError, JSONDecodeError) as exc:
            logger.warning("Failed to read feedback survey history at %s: %s", self._history_path, exc)
            return {"invites_by_phone": {}, "responses": []}
        if not isinstance(payload, dict):
            return {"invites_by_phone": {}, "responses": []}
        payload.setdefault("invites_by_phone", {})
        payload.setdefault("responses", [])
        return payload

    def _write_history(self, history: dict[str, Any]) -> None:
        self._history_path.parent.mkdir(parents=True, exist_ok=True)
        self._history_path.write_text(
            json.dumps(history, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()


feedback_survey_service = FeedbackSurveyService(
    history_path=Path(settings.feedback_survey_history_path),
    enabled=settings.feedback_survey_enabled,
    survey_message=settings.feedback_survey_message_template,
    from_phone=settings.twilio_phone_number,
    twilio_client=settings.twilio_client,
)
