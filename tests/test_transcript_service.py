import json
import shutil
import unittest
from pathlib import Path

from app.models.call import CallConfig, CallSession, TranscriptEntry
from app.services.conversation_anonymizer import AnonymizedConversationSummary
from app.services.transcript_service import _build_session_record, _write_session_logs


class TranscriptServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_root = Path("tests") / ".tmp_transcript_logs" / self._testMethodName
        shutil.rmtree(self.temp_root, ignore_errors=True)
        self.temp_root.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.temp_root, ignore_errors=True)

    def test_session_record_persists_only_privacy_reduced_fields(self):
        session = CallSession(
            call_sid="CA123",
            stream_sid="MZ123",
            config=CallConfig(language="fi", voice="shimmer", temperature=0.6),
            metadata={
                "direction": "outbound",
                "to_number": "+358401234567",
                "from_number": "+14780000000",
                "request_payload": {"phone_number": "+358401234567"},
            },
            status="completed",
            created_at="2026-05-19T08:00:00+00:00",
            started_at="2026-05-19T08:01:00+00:00",
            ended_at="2026-05-19T08:03:00+00:00",
        )
        session.transcript_entries = [
            TranscriptEntry(speaker="user", text="My number is +358401234567"),
            TranscriptEntry(speaker="assistant", text="I can help with booking."),
        ]
        summary = AnonymizedConversationSummary(
            summary="Asiakas kysyi varauksesta ja tunnistetiedot poistettiin.",
            caller_intent="Varausta koskeva kysely.",
            outcome="Varausta koskevat tiedot annettiin.",
            topics=["varaus"],
            follow_up_needed=False,
            reservation_created=False,
            first_user_utterance_redacted="Asiakas kertoi numeronsa [puhelin].",
            redaction_notes=["puhelinnumero poistettu"],
            anonymization_method="openai_llm",
        )

        record = _build_session_record(session, summary.to_dict())

        self.assertEqual(record["privacy_mode"], "llm_anonymized_summary")
        self.assertFalse(record["raw_transcript_persisted"])
        self.assertNotIn("transcript_entries", record)
        self.assertNotIn("dialogue_turns", record)
        self.assertEqual(record["metadata"]["counterparty_label"], "***4567")
        self.assertEqual(record["anonymized_summary"]["summary"], summary.summary)

    def test_redacted_metadata_carries_reservation_signal_with_no_caller_identifying_key(self):
        session = CallSession(
            call_sid="CA321",
            stream_sid="MZ321",
            config=CallConfig(language="fi", voice="shimmer", temperature=0.6),
            metadata={
                "direction": "inbound",
                "from_number": "+358401234567",
                "create_reservation_history": [
                    {
                        "unit_id": "jokipuistopark-asunto-2",
                        "arrival_date": "2026-10-01",
                        "departure_date": "2026-10-03",
                        "reservation_id": "R1",
                    }
                ],
            },
            status="completed",
            created_at="2026-05-19T08:00:00+00:00",
            started_at="2026-05-19T08:01:00+00:00",
            ended_at="2026-05-19T08:03:00+00:00",
        )
        summary = AnonymizedConversationSummary(
            summary="Asiakas varasi majoituksen.",
            caller_intent="Varaus.",
            outcome="Varaus tehtiin.",
            topics=["varaus"],
            follow_up_needed=False,
            reservation_created=True,
            first_user_utterance_redacted="Asiakas halusi varata huoneen.",
            redaction_notes=[],
            anonymization_method="openai_llm",
        )

        record = _build_session_record(session, summary.to_dict())

        self.assertTrue(record["metadata"]["reservation_created"])
        self.assertEqual(record["metadata"]["reservation_count"], 1)
        self.assertEqual(
            set(record["metadata"].keys()),
            {"direction", "counterparty_label", "has_last_error", "reservation_created", "reservation_count"},
        )

    def test_write_session_logs_creates_session_and_summary_files_without_raw_turns_file(self):
        session = CallSession(
            call_sid="CA999",
            stream_sid="MZ999",
            config=CallConfig(language="fi"),
            metadata={"direction": "inbound", "from_number": "+358409999999"},
            status="completed",
            created_at="2026-05-19T08:00:00+00:00",
            started_at="2026-05-19T08:00:10+00:00",
            ended_at="2026-05-19T08:01:10+00:00",
        )
        session.transcript_entries = [
            TranscriptEntry(speaker="user", text="Need room availability in June."),
            TranscriptEntry(speaker="assistant", text="I can help with that."),
        ]
        summary = AnonymizedConversationSummary(
            summary="Asiakas kysyi kesäkuun saatavuudesta.",
            caller_intent="Saatavuutta koskeva kysely.",
            outcome="Saatavuusohje annettiin.",
            topics=["saatavuus"],
            follow_up_needed=False,
            reservation_created=False,
            first_user_utterance_redacted="Asiakas kysyi huoneen saatavuutta kesäkuussa.",
            redaction_notes=["päivämäärä yleistetty"],
            anonymization_method="fallback_redaction",
        )

        from app.config.settings import settings

        previous_dir = settings.conversation_log_dir
        try:
            object.__setattr__(settings, "conversation_log_dir", str(self.temp_root))
            dialogue_turns = _write_session_logs(session, summary)
        finally:
            object.__setattr__(settings, "conversation_log_dir", previous_dir)

        self.assertEqual(len(dialogue_turns), 2)
        files = {path.name for path in self.temp_root.iterdir()}
        self.assertTrue(any(name.startswith("session_MZ999_") for name in files))
        self.assertTrue(any(name.startswith("conversation_summary_MZ999_") for name in files))
        self.assertFalse(any(name.startswith("conversation_turns_MZ999_") for name in files))

        session_file = next(path for path in self.temp_root.iterdir() if path.name.startswith("session_MZ999_"))
        payload = json.loads(session_file.read_text(encoding="utf-8"))
        self.assertEqual(payload["anonymized_summary"]["topics"], ["saatavuus"])


if __name__ == "__main__":
    unittest.main()
