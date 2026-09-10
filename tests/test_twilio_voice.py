import os
import unittest
from dataclasses import replace
from unittest.mock import patch

from app.config.settings import Settings
from app.services import twilio_voice


class TwilioVoiceGreetingTests(unittest.TestCase):
    def test_finnish_greeting_includes_ai_disclosure_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            test_settings = Settings.from_env()

        with patch.object(twilio_voice, "settings", test_settings):
            greeting, language = twilio_voice.get_incoming_call_greeting("fi")

        self.assertEqual(language, "fi-FI")
        self.assertEqual(
            greeting,
            (
                "Puhut tekoälyavustajan kanssa, joka on kiireisinä aikoina osa "
                "Hotelli Framin tiimiä. Yhdistan puhelusi nyt."
            ),
        )

    def test_disclosure_can_be_disabled(self):
        with patch.dict(os.environ, {}, clear=True):
            test_settings = replace(
                Settings.from_env(),
                twilio_ai_disclosure_enabled=False,
            )

        with patch.object(twilio_voice, "settings", test_settings):
            greeting, language = twilio_voice.get_incoming_call_greeting("en")

        self.assertEqual(language, "en-US")
        self.assertEqual(greeting, "Connecting you now.")

    def test_preamble_can_be_disabled_entirely(self):
        with patch.dict(os.environ, {}, clear=True):
            test_settings = replace(
                Settings.from_env(),
                twilio_preamble_enabled=False,
            )

        with patch.object(twilio_voice, "settings", test_settings):
            greeting, language = twilio_voice.get_incoming_call_greeting("fi")

        self.assertEqual(language, "fi-FI")
        self.assertEqual(greeting, "")

    def test_english_disclosure_message_can_be_overridden(self):
        with patch.dict(os.environ, {}, clear=True):
            test_settings = replace(
                Settings.from_env(),
                twilio_ai_disclosure_message_en="This call is handled by an AI assistant.",
            )

        with patch.object(twilio_voice, "settings", test_settings):
            greeting, language = twilio_voice.get_incoming_call_greeting("en")

        self.assertEqual(language, "en-US")
        self.assertEqual(
            greeting,
            "This call is handled by an AI assistant. Connecting you now.",
        )


if __name__ == "__main__":
    unittest.main()
