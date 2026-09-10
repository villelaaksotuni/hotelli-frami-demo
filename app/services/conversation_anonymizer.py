from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import asdict, dataclass
from typing import Any
from urllib import error, request

from app.config.settings import settings
from app.models.call import CallSession, ConversationLog
from app.services.topic_taxonomy import infer_topic_keys, to_finnish_topic_labels, topic_label_fi

logger = logging.getLogger(__name__)

PHONE_PATTERN = re.compile(r"(?<!\w)(?:\+?\d[\d\s\-()]{5,}\d)")
EMAIL_PATTERN = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
URL_PATTERN = re.compile(r"https?://\S+")
BOOKING_REFERENCE_PATTERN = re.compile(r"\b[A-Z]{2,}\d{3,}\b")
DATE_PATTERN = re.compile(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b")
LONG_NUMBER_PATTERN = re.compile(r"\b\d{5,}\b")


@dataclass(frozen=True)
class AnonymizedConversationSummary:
    summary: str
    caller_intent: str
    outcome: str
    topics: list[str]
    follow_up_needed: bool
    booking_link_shared: bool
    first_user_utterance_redacted: str
    redaction_notes: list[str]
    anonymization_method: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ConversationAnonymizer:
    def __init__(
        self,
        *,
        model: str,
        timeout_seconds: float,
        max_input_chars: int,
        enabled: bool,
    ) -> None:
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._max_input_chars = max_input_chars
        self._enabled = enabled

    async def summarize_session(self, session: CallSession) -> AnonymizedConversationSummary:
        dialogue_turns = session.merged_dialogue_turns()
        if not self._enabled:
            return self._build_fallback_summary(
                dialogue_turns,
                reason="llm_anonymization_disabled",
            )

        try:
            return await asyncio.to_thread(self._summarize_with_model, session, dialogue_turns)
        except Exception as exc:
            logger.warning(
                "Failed to build LLM anonymized summary for stream_sid=%s: %s",
                session.stream_sid,
                exc,
            )
            return self._build_fallback_summary(
                dialogue_turns,
                reason="llm_anonymization_fallback",
            )

    def _summarize_with_model(
        self,
        session: CallSession,
        dialogue_turns: ConversationLog,
    ) -> AnonymizedConversationSummary:
        effective_key = settings.azure_openai_api_key if settings.is_azure_openai else settings.openai_api_key
        if not effective_key:
            raise ValueError("Missing API key for log anonymization.")

        response_payload = self._call_openai_chat_completions(
            transcript=self._format_dialogue_turns(dialogue_turns),
            session=session,
        )
        content = (
            response_payload["choices"][0]["message"]["content"]
            if response_payload.get("choices")
            else ""
        )
        parsed = json.loads(content)
        return AnonymizedConversationSummary(
            summary=self._clean_text(parsed.get("summary"), fallback="Yhteenveto ei ole saatavilla."),
            caller_intent=self._clean_text(
                parsed.get("caller_intent"),
                fallback="Yleinen asiakaspalvelukysely.",
            ),
            outcome=self._clean_text(parsed.get("outcome"), fallback="Lopputulos jäi epäselväksi."),
            topics=self._clean_topics(parsed.get("topics")),
            follow_up_needed=bool(parsed.get("follow_up_needed", False)),
            booking_link_shared=bool(parsed.get("booking_link_shared", False)),
            first_user_utterance_redacted=self._clean_text(
                parsed.get("first_user_utterance_redacted"),
                fallback="",
            ),
            redaction_notes=self._clean_notes(parsed.get("redaction_notes")),
            anonymization_method="azure_openai_llm" if settings.is_azure_openai else "openai_llm",
        )

    def _call_openai_chat_completions(
        self,
        *,
        transcript: str,
        session: CallSession,
    ) -> dict[str, Any]:
        if settings.is_azure_openai:
            endpoint = (settings.azure_openai_endpoint or "").rstrip("/")
            deployment = settings.azure_openai_chat_deployment or ""
            url = (
                f"{endpoint}/openai/deployments/{deployment}/chat/completions"
                f"?api-version={settings.azure_openai_chat_api_version}"
            )
            auth_headers = {"api-key": settings.azure_openai_api_key or ""}
        else:
            url = "https://api.openai.com/v1/chat/completions"
            auth_headers = {"Authorization": f"Bearer {settings.openai_api_key}"}

        payload: dict[str, Any] = {
            "store": False,
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a privacy-focused call log summarizer. "
                        "Convert the provided customer support call transcript into a short operational summary "
                        "while removing or generalizing all directly or indirectly identifying personal data. "
                        "All output must always be in Finnish, even if the call itself happened in another language. "
                        "Do not include names, phone numbers, email addresses, exact addresses, booking references, "
                        "or exact travel dates unless they are generalized. Replace sensitive details with broad Finnish "
                        "terms like '[soittaja]', '[puhelin]', '[sähköposti]', '[linkki]', '[varausnumero]' or "
                        "'kesäkuun puolivälissä'. "
                        "Never output the full transcript. Never quote long verbatim passages. "
                        "The field 'first_user_utterance_redacted' must be a short Finnish paraphrase of the caller's "
                        "opening request, not a verbatim quote. "
                        "The field 'topics' must contain concise Finnish topic labels, for example 'varaus', "
                        "'saatavuus' or 'hinta'. "
                        "Produce compact structured JSON only."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "language": session.config.language,
                            "direction": (session.metadata or {}).get("direction"),
                            "transcript": transcript,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "anonymized_call_summary",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "summary": {"type": "string"},
                            "caller_intent": {"type": "string"},
                            "outcome": {"type": "string"},
                            "topics": {
                                "type": "array",
                                "items": {"type": "string"},
                                "maxItems": 6,
                            },
                            "follow_up_needed": {"type": "boolean"},
                            "booking_link_shared": {"type": "boolean"},
                            "first_user_utterance_redacted": {"type": "string"},
                            "redaction_notes": {
                                "type": "array",
                                "items": {"type": "string"},
                                "maxItems": 5,
                            },
                        },
                        "required": [
                            "summary",
                            "caller_intent",
                            "outcome",
                            "topics",
                            "follow_up_needed",
                            "booking_link_shared",
                            "first_user_utterance_redacted",
                            "redaction_notes",
                        ],
                    },
                },
            },
        }
        if not settings.is_azure_openai:
            payload["model"] = self._model
        http_request = request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                **auth_headers,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(http_request, timeout=self._timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI anonymizer request failed: {exc.code} {error_body}") from exc

    def _build_fallback_summary(
        self,
        dialogue_turns: ConversationLog,
        *,
        reason: str,
    ) -> AnonymizedConversationSummary:
        first_user_utterance = self._first_user_utterance(dialogue_turns)
        # No reliable transcript signal exists for this once the booking-link SMS
        # tool was removed (02-02); a synthetic reservation confirmation is read
        # back verbally instead of texted as a link.
        booking_link_shared = False
        topics = self._infer_topics(self._format_dialogue_turns(dialogue_turns))
        redacted_utterance = self._build_fallback_opening_note(first_user_utterance, topics)
        return AnonymizedConversationSummary(
            summary="Automaattista anonymisoitua yhteenvetoa ei saatu muodostettua, joten talteen jäi vain suppeat puhelumuistiinpanot.",
            caller_intent=(
                "Asiakas kysyi aiheesta " + ", ".join(topics[:2])
                if topics
                else "Yleinen asiakaspalvelukysely."
            ),
            outcome="Lopputulosta ei voitu tiivistää, koska anonymisoitu yhteenveto ei ollut käytettävissä.",
            topics=topics,
            follow_up_needed=False,
            booking_link_shared=booking_link_shared,
            first_user_utterance_redacted=redacted_utterance,
            redaction_notes=[self._translate_fallback_reason(reason), "raakaa_transkriptiota_ei_tallennettu"],
            anonymization_method="fallback_redaction",
        )

    def _format_dialogue_turns(self, dialogue_turns: ConversationLog) -> str:
        lines = []
        char_count = 0
        for turn in dialogue_turns:
            speaker = str(turn.get("speaker") or "unknown").strip().lower()
            text = str(turn.get("text") or "").strip()
            if not text:
                continue
            line = f"{speaker}: {text}"
            remaining = self._max_input_chars - char_count
            if remaining <= 0:
                break
            if len(line) > remaining:
                lines.append(line[:remaining].rstrip())
                break
            lines.append(line)
            char_count += len(line) + 1
        return "\n".join(lines)

    def _infer_topics(self, text: str) -> list[str]:
        return [topic_label_fi(topic_key) for topic_key in infer_topic_keys(text)]

    def _first_user_utterance(self, dialogue_turns: ConversationLog) -> str:
        for turn in dialogue_turns:
            if str(turn.get("speaker") or "").strip().lower() != "user":
                continue
            text = str(turn.get("text") or "").strip()
            if text:
                return text
        return ""

    def _redact_text(self, value: str) -> str:
        redacted = EMAIL_PATTERN.sub("[sähköposti]", value)
        redacted = PHONE_PATTERN.sub("[puhelin]", redacted)
        redacted = URL_PATTERN.sub("[linkki]", redacted)
        redacted = BOOKING_REFERENCE_PATTERN.sub("[varausnumero]", redacted)
        redacted = DATE_PATTERN.sub("[päivämäärä]", redacted)
        redacted = LONG_NUMBER_PATTERN.sub("[numero]", redacted)
        return self._clean_text(redacted, fallback="")

    @staticmethod
    def _clean_text(value: Any, *, fallback: str) -> str:
        cleaned = " ".join(str(value or "").split()).strip()
        return cleaned if cleaned else fallback

    def _clean_topics(self, value: Any) -> list[str]:
        return to_finnish_topic_labels(value)

    def _clean_notes(self, value: Any) -> list[str]:
        notes = []
        for item in value or []:
            cleaned = self._clean_text(item, fallback="")
            if cleaned and cleaned not in notes:
                notes.append(cleaned)
        return notes[:5]

    def _build_fallback_opening_note(self, first_user_utterance: str, topics: list[str]) -> str:
        if topics:
            return "Asiakas aloitti puhelun aiheesta " + ", ".join(topics[:2]) + "."
        if self._redact_text(first_user_utterance):
            return "Asiakas kertoi asiansa puhelun alussa, mutta tarkka sanamuoto jätettiin tallentamatta."
        return "Asiakas kertoi asiansa puhelun alussa."

    @staticmethod
    def _translate_fallback_reason(reason: str) -> str:
        mapping = {
            "llm_anonymization_disabled": "llm_anonymisointi_poistettu_käytöstä",
            "llm_anonymization_fallback": "llm_anonymisointi_epäonnistui",
        }
        return mapping.get(reason, "anonymisoinnin_varatila")


conversation_anonymizer = ConversationAnonymizer(
    model=settings.log_anonymizer_model,
    timeout_seconds=settings.log_anonymizer_timeout_seconds,
    max_input_chars=settings.log_anonymizer_max_input_chars,
    enabled=settings.log_anonymization_enabled,
)
