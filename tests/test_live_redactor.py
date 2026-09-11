import unittest

from app.services.live_redactor import (
    NAME_PLACEHOLDER,
    PHONE_PLACEHOLDER,
    redact_for_broadcast,
)


class LiveRedactorTests(unittest.TestCase):
    def test_bare_finnish_mobile_number_is_replaced(self):
        result = redact_for_broadcast("Numeroni on 0401234567")

        self.assertIn(PHONE_PLACEHOLDER, result)
        self.assertNotIn("0401234567", result)
        self.assertNotIn("401234567", result)

    def test_international_form_is_replaced(self):
        result = redact_for_broadcast("Soita numeroon +358 40 123 4567")

        self.assertIn(PHONE_PLACEHOLDER, result)
        self.assertNotIn("358", result)
        self.assertNotIn("4567", result)

    def test_spaced_form_is_replaced(self):
        result = redact_for_broadcast("Numeroni on 040 123 4567")

        self.assertIn(PHONE_PLACEHOLDER, result)
        self.assertNotIn("4567", result)

    def test_dashed_form_is_replaced(self):
        result = redact_for_broadcast("Numeroni on 040-123-4567")

        self.assertIn(PHONE_PLACEHOLDER, result)
        self.assertNotIn("4567", result)

    def test_nimeni_on_phrasing_preserves_intro_and_redacts_name(self):
        result = redact_for_broadcast("nimeni on Matti")

        self.assertIn("nimeni on", result)
        self.assertIn(NAME_PLACEHOLDER, result)
        self.assertNotIn("Matti", result)

    def test_olen_phrasing_preserves_intro_and_redacts_name(self):
        result = redact_for_broadcast("olen Liisa")

        self.assertIn("olen", result)
        self.assertIn(NAME_PLACEHOLDER, result)
        self.assertNotIn("Liisa", result)

    def test_self_id_match_is_case_insensitive_and_handles_diacritics(self):
        result_upper_phrase = redact_for_broadcast("OLEN Ähtäri")
        result_mixed = redact_for_broadcast("Nimeni On Örjan")

        self.assertIn(NAME_PLACEHOLDER, result_upper_phrase)
        self.assertNotIn("Ähtäri", result_upper_phrase)
        self.assertIn(NAME_PLACEHOLDER, result_mixed)
        self.assertNotIn("Örjan", result_mixed)

    def test_ordinary_speech_passes_through_unchanged(self):
        text = "Haluaisin varata huoneen kahdeksi yoksi"

        self.assertEqual(redact_for_broadcast(text), text)

    def test_non_phone_shaped_short_numerals_are_not_redacted(self):
        self.assertEqual(redact_for_broadcast("kaksi yota"), "kaksi yota")
        self.assertEqual(redact_for_broadcast("3"), "3")

    def test_empty_string_returns_empty_string_without_raising(self):
        self.assertEqual(redact_for_broadcast(""), "")

    def test_sentence_with_both_phone_and_name_is_fully_covered(self):
        result = redact_for_broadcast("olen Matti, numeroni on 0401234567")

        self.assertIn(NAME_PLACEHOLDER, result)
        self.assertIn(PHONE_PLACEHOLDER, result)
        self.assertNotIn("Matti", result)
        self.assertNotIn("0401234567", result)


if __name__ == "__main__":
    unittest.main()
