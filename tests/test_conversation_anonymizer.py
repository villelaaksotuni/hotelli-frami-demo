import json
import unittest
from dataclasses import replace
from unittest.mock import patch

from app.models.call import CallConfig, CallSession, TranscriptEntry
from app.services import conversation_anonymizer as anonymizer_module
from app.services.conversation_anonymizer import ConversationAnonymizer


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class ConversationAnonymizerTests(unittest.TestCase):
    def test_azure_chat_completion_uses_configured_api_version_and_deployment_path(self):
        session = CallSession(
            call_sid="CA123",
            stream_sid="MZ123",
            config=CallConfig(language="fi"),
        )
        session.transcript_entries = [
            TranscriptEntry(speaker="user", text="Tarvitsen majoitusta."),
            TranscriptEntry(speaker="assistant", text="Autan mielelläni."),
        ]
        anonymizer = ConversationAnonymizer(
            model="gpt-4o-mini",
            timeout_seconds=5,
            max_input_chars=2000,
            enabled=True,
        )
        response_payload = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "summary": "Asiakas kysyi majoituksesta.",
                                "caller_intent": "Majoituskysely.",
                                "outcome": "Yhteenveto muodostettiin.",
                                "topics": ["varaus"],
                                "follow_up_needed": False,
                                "first_user_utterance_redacted": "Asiakas kysyi majoitusta.",
                                "redaction_notes": [],
                            },
                            ensure_ascii=False,
                        )
                    }
                }
            ]
        }
        captured = {}

        def fake_urlopen(http_request, timeout):
            captured["url"] = http_request.full_url
            captured["timeout"] = timeout
            captured["headers"] = dict(http_request.header_items())
            captured["body"] = json.loads(http_request.data.decode("utf-8"))
            return _FakeResponse(response_payload)

        test_settings = replace(
            anonymizer_module.settings,
            openai_api_provider="azure-openai",
            azure_openai_api_key="azure-key",
            azure_openai_endpoint="https://example-resource.openai.azure.com/",
            azure_openai_chat_deployment="o4-mini",
            azure_openai_chat_api_version="2024-12-01-preview",
        )

        with patch.object(anonymizer_module, "settings", test_settings):
            with patch("app.services.conversation_anonymizer.request.urlopen", side_effect=fake_urlopen):
                summary = anonymizer._summarize_with_model(session, session.merged_dialogue_turns())

        self.assertEqual(
            captured["url"],
            "https://example-resource.openai.azure.com/openai/deployments/o4-mini/chat/completions?api-version=2024-12-01-preview",
        )
        self.assertEqual(captured["timeout"], 5)
        self.assertEqual(captured["headers"]["Api-key"], "azure-key")
        self.assertNotIn("model", captured["body"])
        self.assertEqual(summary.anonymization_method, "azure_openai_llm")

    def test_reservation_created_is_false_with_no_history(self):
        session = CallSession(
            call_sid="CA124",
            stream_sid="MZ124",
            config=CallConfig(language="fi"),
        )
        anonymizer = ConversationAnonymizer(
            model="gpt-4o-mini",
            timeout_seconds=5,
            max_input_chars=2000,
            enabled=False,
        )

        summary = anonymizer._build_fallback_summary(
            session.merged_dialogue_turns(),
            session=session,
            reason="llm_anonymization_disabled",
        )

        self.assertFalse(summary.reservation_created)

    def test_reservation_created_is_true_with_one_history_entry(self):
        session = CallSession(
            call_sid="CA125",
            stream_sid="MZ125",
            config=CallConfig(language="fi"),
        )
        session.metadata["create_reservation_history"] = [
            {"unit_id": "jokipuistopark-asunto-2", "arrival_date": "2026-10-01", "departure_date": "2026-10-03", "reservation_id": "R1"}
        ]
        anonymizer = ConversationAnonymizer(
            model="gpt-4o-mini",
            timeout_seconds=5,
            max_input_chars=2000,
            enabled=False,
        )

        summary = anonymizer._build_fallback_summary(
            session.merged_dialogue_turns(),
            session=session,
            reason="llm_anonymization_disabled",
        )

        self.assertTrue(summary.reservation_created)

    def test_booking_words_in_transcript_with_empty_history_stay_false(self):
        session = CallSession(
            call_sid="CA126",
            stream_sid="MZ126",
            config=CallConfig(language="fi"),
        )
        session.transcript_entries = [
            TranscriptEntry(speaker="user", text="Haluaisin tehda varauksen huomiseksi."),
            TranscriptEntry(speaker="assistant", text="Toki, katsotaan saatavuus."),
        ]
        anonymizer = ConversationAnonymizer(
            model="gpt-4o-mini",
            timeout_seconds=5,
            max_input_chars=2000,
            enabled=False,
        )

        summary = anonymizer._build_fallback_summary(
            session.merged_dialogue_turns(),
            session=session,
            reason="llm_anonymization_disabled",
        )

        self.assertFalse(summary.reservation_created)


if __name__ == "__main__":
    unittest.main()
