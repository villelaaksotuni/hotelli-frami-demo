import inspect
import unittest

from app.services.content_policy import (
    CONTENT_POLICY_PLACEHOLDER,
    apply_content_policy,
)
from app.services.live_broadcast import LiveBroadcastHub, TRANSCRIPT_SANITIZERS
from app.services.live_redactor import redact_for_broadcast


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

    def test_fronted_object_threat_word_order_is_blocked(self):
        # WR-02: Finnish word order is flexible — the object-pronoun-then-verb
        # order is a grammatical variant of the same threat THREAT_PATTERN
        # already catches in verb-then-pronoun order.
        self.assertEqual(apply_content_policy("sinut tapan"), CONTENT_POLICY_PLACEHOLDER)
        self.assertEqual(
            apply_content_policy("sinut minä tapan"), CONTENT_POLICY_PLACEHOLDER
        )
        self.assertEqual(
            apply_content_policy("Kuule, sinut minä tapan heti"),
            CONTENT_POLICY_PLACEHOLDER,
        )

    def test_ordinary_meeting_verb_is_not_mistaken_for_threat(self):
        # "tapaan" (I will meet) must not be conflated with "tapan" (I kill)
        # by either the verb-first or fronted-object threat pattern.
        verb_first = "Tapaan teidät huomenna kello kymmenen"
        object_first = "Teidät tapaan huomenna kello kymmenen"

        self.assertEqual(apply_content_policy(verb_first), verb_first)
        self.assertEqual(apply_content_policy(object_first), object_first)


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


# The over-filtering corpus below is the guard against repeating the 03-05
# over-redaction defect (see .planning/STATE.md's Phase 03 decision log): a future
# maintainer tempted to broaden BLOCKED_PATTERNS should see this corpus go red
# before shipping a change that blanks ordinary Finnish speech. Each utterance is
# asserted byte-identical against apply_content_policy's input, not merely "no
# placeholder present", so a partial substitution also fails this guard.
ORDINARY_FINNISH_UTTERANCES: tuple[str, ...] = (
    "Haluaisin varata huoneen saapumispäivälle 2025-09-10",
    "Hinta on 129 euroa yöltä",
    "Varaus on kahdeksi yöksi ja kahdelle vieraalle",
    "Onko Jokipuisto-alueella vapaita huoneita",
    "Haluaisin huoneen nimeltä Rantasauna",
    # Lowercase self-identification of the shape the PII redactor deliberately does
    # not match (live_redactor.py's CR-02: SELF_ID_PATTERN requires a capitalized
    # name) — content policy must not treat it differently.
    "olen matti ja haluaisin varata huoneen",
    "Voinko maksaa varauksen luottokortilla",
    "Mihin aikaan sisäänkirjautuminen alkaa",
    "Haluaisin perua varaukseni",
    "Kiitos paljon, hyvää päivänjatkoa",
    "vittu tämä on hankalaa",
    "saatana, en löydä varausnumeroa",
    "perkele, yhteys taitaa pätkiä",
    "Onko aamiainen sisällytetty hintaan",
    "Voisitteko lähettää vahvistuksen sähköpostitse",
)


class ContentPolicyOverFilteringCorpusTests(unittest.TestCase):
    def test_ordinary_utterances_pass_through_byte_identical(self):
        for text in ORDINARY_FINNISH_UTTERANCES:
            with self.subTest(text=text):
                self.assertEqual(apply_content_policy(text), text)


class BothSanitizersInvariantTests(unittest.TestCase):
    def test_utterance_requiring_both_sanitizers_yields_content_policy_placeholder(self):
        # Carries a Finnish phone number (redactor's job) AND a blocked term
        # (content policy's job) — proving the content policy ran AFTER the
        # redactor rather than instead of it.
        hub = LiveBroadcastHub()
        queue = hub.register()

        hub.publish_transcript(
            speaker="user", text="Numeroni on 0401234567, tapan sinut"
        )

        event = queue.get_nowait()
        self.assertEqual(event["text"], CONTENT_POLICY_PLACEHOLDER)

    def test_utterance_only_redactor_would_change_still_gets_redacted(self):
        # Proves the content policy did not swallow the redactor's own output.
        hub = LiveBroadcastHub()
        queue = hub.register()

        hub.publish_transcript(speaker="user", text="Numeroni on 0401234567")

        event = queue.get_nowait()
        self.assertEqual(event["text"], redact_for_broadcast("Numeroni on 0401234567"))

    def test_sanitizer_order_is_exactly_redactor_then_content_policy(self):
        expected = [redact_for_broadcast, apply_content_policy]
        actual = list(TRANSCRIPT_SANITIZERS)

        self.assertEqual(
            actual,
            expected,
            msg=(
                "TRANSCRIPT_SANITIZERS must be exactly "
                "[redact_for_broadcast, apply_content_policy] in that order — "
                f"got {[getattr(fn, '__name__', fn) for fn in actual]}"
            ),
        )


class PublishAgentStateSanitizationTests(unittest.TestCase):
    # CR-01: publish_agent_state is a second, independent publish path that
    # projects raw tool-call arguments (e.g. unitName, a caller-influenced
    # free-text field) straight onto the public live board. It must run the
    # same TRANSCRIPT_SANITIZERS composition as publish_transcript.
    def test_blocked_slot_value_reaches_subscriber_as_placeholder(self):
        hub = LiveBroadcastHub()
        queue = hub.register()

        hub.publish_agent_state(
            tool="check_availability", arguments={"unitName": "tapan sinut"}
        )

        event = queue.get_nowait()
        self.assertEqual(event["type"], "agent")
        self.assertEqual(event["slots"]["unitName"], CONTENT_POLICY_PLACEHOLDER)
        self.assertNotIn("tapan", event["slots"]["unitName"])

    def test_blocked_slot_value_is_sanitized_in_state_snapshot(self):
        hub = LiveBroadcastHub()

        hub.publish_agent_state(
            tool="check_availability", arguments={"unitName": "senkin huora"}
        )

        snapshot = hub.state_snapshot()
        self.assertEqual(
            snapshot["agent"]["slots"]["unitName"], CONTENT_POLICY_PLACEHOLDER
        )

    def test_ordinary_slot_value_passes_through_unchanged(self):
        hub = LiveBroadcastHub()
        queue = hub.register()

        hub.publish_agent_state(
            tool="check_availability", arguments={"unitName": "Rantasauna"}
        )

        event = queue.get_nowait()
        self.assertEqual(event["slots"]["unitName"], "Rantasauna")


class SingleTranscriptEmissionSiteTests(unittest.TestCase):
    def test_exactly_one_site_emits_a_transcript_type_event(self):
        # If a later phase adds a second transcript-emitting method that skips the
        # sanitizers, this goes red.
        source = inspect.getsource(LiveBroadcastHub)
        occurrences = source.count('"type": "transcript"')

        self.assertEqual(
            occurrences,
            1,
            msg=(
                f"Expected exactly one transcript-type event emission site in "
                f"LiveBroadcastHub, found {occurrences}"
            ),
        )


class PublishTranscriptStaysSynchronousTests(unittest.TestCase):
    def test_publish_transcript_is_not_a_coroutine(self):
        # Companion to RT-03: no future change can slip an `await` into the path
        # that also forwards live audio to the caller.
        self.assertFalse(
            inspect.iscoroutinefunction(LiveBroadcastHub.publish_transcript),
            "publish_transcript became a coroutine",
        )


if __name__ == "__main__":
    unittest.main()
