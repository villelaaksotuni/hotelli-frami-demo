import asyncio
import json
import pathlib
import re
import unittest

from starlette.requests import Request

from app.routes.live import live_page, live_stream
from app.services.live_broadcast import LiveBroadcastHub, live_broadcast_hub


def _build_stream_request(receive) -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": "/api/live/stream",
            "raw_path": b"/api/live/stream",
            "root_path": "",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("demo.example.com", 443),
        },
        receive,
    )


def _hanging_receive():
    async def receive():
        await asyncio.sleep(3600)
        return {"type": "http.disconnect"}

    return receive


def _build_page_request() -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": "/live",
            "raw_path": b"/live",
            "root_path": "",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("demo.example.com", 443),
        }
    )


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


class LiveTranscriptSseEndToEndTests(unittest.TestCase):
    def tearDown(self):
        live_broadcast_hub.reset_call_state()

    def test_sse_subscriber_receives_redacted_transcript_frame(self):
        async def scenario():
            request = _build_stream_request(_hanging_receive())
            response = await live_stream(request)
            body_iterator = response.body_iterator

            first_frame = await asyncio.wait_for(body_iterator.__anext__(), timeout=1)
            first_parsed = json.loads(first_frame.removeprefix("data: ").strip())
            self.assertEqual(first_parsed["type"], "snapshot")

            live_broadcast_hub.publish_transcript(
                speaker="user", text="soita 040 123 4567"
            )

            second_frame = await asyncio.wait_for(body_iterator.__anext__(), timeout=1)
            second_parsed = json.loads(second_frame.removeprefix("data: ").strip())
            self.assertEqual(second_parsed["type"], "transcript")
            self.assertIn("[puhelin]", second_parsed["text"])
            self.assertNotIn("4567", second_parsed["text"])

            await body_iterator.aclose()

        asyncio.run(scenario())


class VoicePublishTranscriptSourceTests(unittest.TestCase):
    def test_exactly_two_unawaited_publish_transcript_call_sites(self):
        voice_source = pathlib.Path("app/routes/voice.py").read_text(encoding="utf-8")

        call_sites = re.findall(r"live_broadcast_hub\.publish_transcript\(", voice_source)
        self.assertEqual(len(call_sites), 2)
        self.assertNotIn("await live_broadcast_hub", voice_source)


class LiveTranscriptPanelHtmlTests(unittest.TestCase):
    def setUp(self):
        response = asyncio.run(live_page(_build_page_request()))
        self.body = response.body.decode("utf-8")

    def test_transcript_panel_declares_max_height_and_overflow_scroll(self):
        self.assertIn("#transcript-list", self.body)
        transcript_rule_match = re.search(
            r"#transcript-list\s*\{([^}]*)\}", self.body
        )
        self.assertIsNotNone(transcript_rule_match)
        rule_body = transcript_rule_match.group(1)
        self.assertIn("max-height", rule_body)
        self.assertIn("overflow-y", rule_body)

    def test_no_truncation_rule_present(self):
        self.assertNotIn("text-overflow: ellipsis", self.body)
        self.assertNotIn("-webkit-line-clamp", self.body)


if __name__ == "__main__":
    unittest.main()
