import unittest

from app.services.content_policy import (
    CONTENT_POLICY_PLACEHOLDER,
    apply_content_policy,
)
from app.services.live_broadcast import LiveBroadcastHub


class ContentPolicyUnitTests(unittest.TestCase):
    def test_blocked_threat_returns_exactly_the_placeholder(self):
        result = apply_content_policy("tapan sinut")

        self.assertEqual(result, CONTENT_POLICY_PLACEHOLDER)

    def test_ordinary_utterance_returns_unchanged(self):
        text = "Haluaisin varata huoneen kahdeksi yoksi"

        self.assertEqual(apply_content_policy(text), text)

    def test_empty_string_returns_unchanged(self):
        self.assertEqual(apply_content_policy(""), "")

    def test_matching_is_case_insensitive_across_inflected_forms(self):
        self.assertEqual(apply_content_policy("TAPAN SINUT"), CONTENT_POLICY_PLACEHOLDER)
        self.assertEqual(
            apply_content_policy("Tapoin sinut eilen leikissä"),
            CONTENT_POLICY_PLACEHOLDER,
        )
        self.assertEqual(
            apply_content_policy("tapaisin sinut jos voisin"),
            CONTENT_POLICY_PLACEHOLDER,
        )

    def test_slur_category_is_blocked(self):
        self.assertEqual(apply_content_policy("senkin ryssä"), CONTENT_POLICY_PLACEHOLDER)

    def test_sexual_insult_category_is_blocked(self):
        self.assertEqual(apply_content_policy("senkin huora"), CONTENT_POLICY_PLACEHOLDER)

    def test_mild_interjection_expletive_is_not_blocked(self):
        # The deliberately-excluded category (CR-03 in content_policy.py): a bare
        # conversational expletive used as punctuation, not aimed at anyone.
        text = "vittu tämä on hankalaa"

        self.assertEqual(apply_content_policy(text), text)

    def test_partial_substitution_never_occurs(self):
        # A match always replaces the WHOLE utterance, never just the offending word.
        result = apply_content_policy("Kuule, tapan sinut heti kun näen sinut")

        self.assertEqual(result, CONTENT_POLICY_PLACEHOLDER)
        self.assertNotIn("Kuule", result)
        self.assertNotIn("heti", result)


class ContentPolicyEndToEndTests(unittest.TestCase):
    def test_blocked_user_utterance_reaches_subscriber_as_placeholder(self):
        hub = LiveBroadcastHub()
        queue = hub.register()

        hub.publish_transcript(speaker="user", text="tapan sinut")

        event = queue.get_nowait()
        self.assertEqual(event["type"], "transcript")
        self.assertEqual(event["text"], CONTENT_POLICY_PLACEHOLDER)
        self.assertNotIn("tapan", event["text"])

    def test_blocked_assistant_utterance_reaches_subscriber_as_placeholder(self):
        hub = LiveBroadcastHub()
        queue = hub.register()

        hub.publish_transcript(speaker="assistant", text="senkin huora")

        event = queue.get_nowait()
        self.assertEqual(event["type"], "transcript")
        self.assertEqual(event["text"], CONTENT_POLICY_PLACEHOLDER)
        self.assertNotIn("huora", event["text"])

    def test_blocked_utterance_is_still_published_not_dropped(self):
        # A visitor must be able to see that a turn happened and was withheld,
        # rather than silently losing the turn from the transcript.
        hub = LiveBroadcastHub()
        queue = hub.register()

        hub.publish_transcript(speaker="user", text="tapan sinut")

        self.assertEqual(queue.qsize(), 1)


if __name__ == "__main__":
    unittest.main()
