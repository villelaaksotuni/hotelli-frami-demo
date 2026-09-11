import unittest

from app.services.live_broadcast import LiveBroadcastHub


class LiveTranscriptHubTests(unittest.TestCase):
    def test_publish_transcript_redacts_phone_number_before_reaching_subscriber(self):
        hub = LiveBroadcastHub()
        queue = hub.register()

        hub.publish_transcript(speaker="user", text="soita 040 123 4567")

        event = queue.get_nowait()
        self.assertIn("[puhelin]", event["text"])
        self.assertNotIn("4567", event["text"])

    def test_publish_transcript_event_keys_are_exactly_type_ts_speaker_text(self):
        hub = LiveBroadcastHub()
        queue = hub.register()

        hub.publish_transcript(speaker="user", text="soita 040 123 4567")

        event = queue.get_nowait()
        self.assertEqual(set(event.keys()), {"type", "ts", "speaker", "text"})
        self.assertEqual(event["type"], "transcript")

    def test_publish_transcript_is_declared_synchronous(self):
        import inspect

        self.assertFalse(inspect.iscoroutinefunction(LiveBroadcastHub.publish_transcript))

    def test_publish_transcript_with_empty_text_after_redaction_does_not_publish(self):
        hub = LiveBroadcastHub()
        queue = hub.register()

        hub.publish_transcript(speaker="user", text="   ")

        self.assertEqual(queue.qsize(), 0)

    def test_publish_transcript_does_not_add_to_state_snapshot(self):
        hub = LiveBroadcastHub()

        hub.publish_transcript(speaker="assistant", text="Tervetuloa Hotelli Framiin.")

        snapshot = hub.state_snapshot()
        self.assertNotIn("transcript", snapshot)


if __name__ == "__main__":
    unittest.main()
