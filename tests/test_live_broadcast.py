import asyncio
import unittest

from app.services.live_broadcast import (
    LIVE_STATUS_CONNECTED,
    LIVE_STATUS_ENDED,
    LIVE_STATUS_ERROR,
    LIVE_STATUS_IN_PROGRESS,
    LIVE_STATUS_RINGING,
    LiveBroadcastHub,
)


class LiveBroadcastHubTests(unittest.TestCase):
    def test_publish_status_stores_and_fans_out_to_all_subscribers(self):
        async def scenario():
            hub = LiveBroadcastHub()
            queue_a = hub.register()
            queue_b = hub.register()

            for state in (
                LIVE_STATUS_RINGING,
                LIVE_STATUS_CONNECTED,
                LIVE_STATUS_IN_PROGRESS,
                LIVE_STATUS_ENDED,
                LIVE_STATUS_ERROR,
            ):
                hub.publish_status(state)
                event_a = queue_a.get_nowait()
                event_b = queue_b.get_nowait()
                self.assertEqual(event_a["state"], state)
                self.assertEqual(event_b["state"], state)
                self.assertEqual(hub.state_snapshot()["status"]["state"], state)

        asyncio.run(scenario())

    def test_late_subscriber_receives_last_status_via_snapshot_without_new_publish(self):
        hub = LiveBroadcastHub()
        hub.publish_status(LIVE_STATUS_IN_PROGRESS)

        snapshot = hub.state_snapshot()

        self.assertEqual(snapshot["status"]["state"], LIVE_STATUS_IN_PROGRESS)

    def test_snapshot_contains_no_transcript_key(self):
        hub = LiveBroadcastHub()
        hub.publish_status(LIVE_STATUS_IN_PROGRESS)

        snapshot = hub.state_snapshot()

        self.assertNotIn("transcript", snapshot)

    def test_ringing_clears_prior_call_state(self):
        hub = LiveBroadcastHub()
        hub.publish_status(LIVE_STATUS_ERROR, reason="media_stream_error")
        hub.publish_status(LIVE_STATUS_RINGING)

        snapshot = hub.state_snapshot()

        self.assertEqual(snapshot["status"]["state"], LIVE_STATUS_RINGING)
        self.assertIsNone(snapshot["status"]["reason"])

    def test_full_subscriber_queue_drops_event_but_publisher_and_others_are_unaffected(self):
        hub = LiveBroadcastHub(queue_maxsize=2)
        full_queue = hub.register()
        other_queue = hub.register()

        full_queue.put_nowait({"type": "status", "state": "filler-1"})
        full_queue.put_nowait({"type": "status", "state": "filler-2"})

        hub.publish_status(LIVE_STATUS_IN_PROGRESS)

        self.assertEqual(full_queue.qsize(), 2)
        self.assertEqual(other_queue.get_nowait()["state"], LIVE_STATUS_IN_PROGRESS)

    def test_reset_call_state_clears_last_status(self):
        hub = LiveBroadcastHub()
        hub.publish_status(LIVE_STATUS_IN_PROGRESS)

        hub.reset_call_state()

        self.assertIsNone(hub.state_snapshot()["status"])

    def test_unregister_removes_subscriber(self):
        hub = LiveBroadcastHub()
        queue = hub.register()
        self.assertEqual(hub.subscriber_count(), 1)

        hub.unregister(queue)

        self.assertEqual(hub.subscriber_count(), 0)


if __name__ == "__main__":
    unittest.main()
