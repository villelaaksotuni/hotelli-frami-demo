import re
import time
import unittest

from app.services.live_broadcast import LiveBroadcastHub
from app.services.live_redactor import (
    MIN_PHONE_DIGITS,
    NAME_PLACEHOLDER,
    PHONE_PATTERN,
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


class LiveRedactorOverRedactionRegressionTests(unittest.TestCase):
    def test_olen_kiinnostunut_sentence_survives_unchanged(self):
        text = "olen kiinnostunut huoneesta"

        self.assertEqual(redact_for_broadcast(text), text)

    def test_olen_valmis_maksamaan_sentence_survives_unchanged(self):
        text = "olen valmis maksamaan"

        self.assertEqual(redact_for_broadcast(text), text)

    def test_olen_samaa_mielta_sentence_survives_unchanged(self):
        text = "olen samaa mielta"

        self.assertEqual(redact_for_broadcast(text), text)

    def test_olen_kaksi_yota_varaamassa_sentence_survives_unchanged(self):
        text = "olen kaksi yota varaamassa"

        self.assertEqual(redact_for_broadcast(text), text)

    def test_uppercase_introducing_phrase_followed_by_lowercase_word_is_not_a_name(self):
        text = "OLEN kiinnostunut huoneesta"

        self.assertEqual(redact_for_broadcast(text), text)

    def test_introducing_phrase_survives_any_casing_while_name_redacts(self):
        result_all_caps = redact_for_broadcast("OLEN Ähtäri")
        result_title_case = redact_for_broadcast("Nimeni On Örjan")

        self.assertIn("OLEN", result_all_caps)
        self.assertIn(NAME_PLACEHOLDER, result_all_caps)
        self.assertNotIn("Ähtäri", result_all_caps)

        self.assertIn("Nimeni On", result_title_case)
        self.assertIn(NAME_PLACEHOLDER, result_title_case)
        self.assertNotIn("Örjan", result_title_case)

    def test_iso_arrival_date_survives_unchanged(self):
        text = "Saapumispäivä on 2025-09-10"

        self.assertEqual(redact_for_broadcast(text), text)

    def test_dotted_finnish_dates_survive_unchanged(self):
        text = "Saapuminen 10.9.2025 ja lähtö 12.9.2025"

        self.assertEqual(redact_for_broadcast(text), text)

    def test_hyphenated_confirmation_number_survives_unchanged(self):
        text = "Varauksen numero on 12-345-678"

        self.assertEqual(redact_for_broadcast(text), text)

    def test_street_house_number_survives_unchanged(self):
        text = "Osoite on Hämeenkatu 12345"

        self.assertEqual(redact_for_broadcast(text), text)

    def test_postal_code_survives_unchanged(self):
        text = "Postinumero on 60100"

        self.assertEqual(redact_for_broadcast(text), text)

    def test_prices_across_magnitudes_survive_unchanged(self):
        self.assertEqual(
            redact_for_broadcast("Hinta on 129 euroa yöltä"),
            "Hinta on 129 euroa yöltä",
        )
        self.assertEqual(
            redact_for_broadcast("Yhteensä 1250 euroa"), "Yhteensä 1250 euroa"
        )
        self.assertEqual(
            redact_for_broadcast("Hinta 12500 euroa"), "Hinta 12500 euroa"
        )


class LiveRedactorPhoneShapeTests(unittest.TestCase):
    def test_bare_finnish_mobile_number_still_redacts(self):
        result = redact_for_broadcast("Numeroni on 0401234567")

        self.assertIn(PHONE_PLACEHOLDER, result)
        self.assertIsNone(re.search(r"\d{4,}", result))

    def test_international_finnish_form_still_redacts(self):
        result = redact_for_broadcast("Soita numeroon +358 40 123 4567")

        self.assertIn(PHONE_PLACEHOLDER, result)
        self.assertIsNone(re.search(r"\d{4,}", result))

    def test_spaced_form_still_redacts(self):
        result = redact_for_broadcast("Numeroni on 040 123 4567")

        self.assertIn(PHONE_PLACEHOLDER, result)
        self.assertIsNone(re.search(r"\d{4,}", result))

    def test_dashed_form_still_redacts(self):
        result = redact_for_broadcast("Numeroni on 040-123-4567")

        self.assertIn(PHONE_PLACEHOLDER, result)
        self.assertIsNone(re.search(r"\d{4,}", result))

    def test_non_finnish_plus_prefixed_number_still_redacts(self):
        result = redact_for_broadcast("+44 20 7946 0958")

        self.assertIn(PHONE_PLACEHOLDER, result)
        self.assertIsNone(re.search(r"\d{4,}", result))

    def test_two_back_to_back_phone_numbers_both_redact_separately(self):
        result = redact_for_broadcast("numeroni on 0401234567 0509876543")

        self.assertEqual(result.count(PHONE_PLACEHOLDER), 2)
        self.assertIsNone(re.search(r"\d{4,}", result))

    def test_digit_count_guard_is_reachable_and_rejects_short_code(self):
        text = "koodi 01-2-3-4 on kaytossa"

        self.assertIsNotNone(PHONE_PATTERN.search(text))
        self.assertEqual(redact_for_broadcast(text), text)

    def test_min_phone_digits_is_seven(self):
        self.assertEqual(MIN_PHONE_DIGITS, 7)

    def test_redaction_cost_stays_negligible_on_adversarial_input(self):
        text = ("0444 -()" * 60) + "olen " + ("Aa" * 40)

        start = time.perf_counter()
        for _ in range(2000):
            redact_for_broadcast(text)
        elapsed = time.perf_counter() - start

        self.assertLess(elapsed, 2.0)


class LiveRedactorBroadcastBoundaryTests(unittest.TestCase):
    def test_ordinary_sentence_reaches_a_subscriber_byte_identical(self):
        hub = LiveBroadcastHub()
        queue = hub.register()

        hub.publish_transcript(speaker="user", text="olen kiinnostunut huoneesta")

        event = queue.get_nowait()
        self.assertEqual(event["text"], "olen kiinnostunut huoneesta")


if __name__ == "__main__":
    unittest.main()
