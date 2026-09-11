import asyncio
import json
import unittest
from unittest import mock

from starlette.requests import Request

import app.routes.live as live_module
from app.routes.live import live_stream
from app.services.live_broadcast import live_broadcast_hub


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


def _disconnecting_receive():
    async def receive():
        return {"type": "http.disconnect"}

    return receive


class LiveStreamEndToEndTests(unittest.TestCase):
    def tearDown(self):
        live_broadcast_hub.reset_call_state()

    def test_status_published_from_call_path_reaches_subscriber(self):
        async def scenario():
            request = _build_stream_request(_hanging_receive())
            response = await live_stream(request)

            body_iterator = response.body_iterator

            first_frame = await asyncio.wait_for(body_iterator.__anext__(), timeout=1)
            first_parsed = json.loads(first_frame.removeprefix("data: ").strip())
            self.assertEqual(first_parsed["type"], "snapshot")

            live_broadcast_hub.publish_status("in_progress")

            second_frame = await asyncio.wait_for(body_iterator.__anext__(), timeout=1)
            second_parsed = json.loads(second_frame.removeprefix("data: ").strip())
            self.assertEqual(second_parsed["type"], "status")
            self.assertEqual(second_parsed["state"], "in_progress")

            await body_iterator.aclose()

        asyncio.run(scenario())

    def test_live_routes_registered_on_app(self):
        from app.main import app

        paths = [route.path for route in app.routes if hasattr(route, "path")]
        self.assertIn("/live", paths)
        self.assertIn("/api/live/stream", paths)

    def test_voice_module_publishes_status(self):
        import pathlib

        voice_source = pathlib.Path("app/routes/voice.py").read_text(encoding="utf-8")
        self.assertIn("live_broadcast_hub.publish_status(", voice_source)

    def test_late_subscriber_snapshot_carries_current_status_with_no_transcript(self):
        async def scenario():
            live_broadcast_hub.publish_status("in_progress")

            request = _build_stream_request(_hanging_receive())
            response = await live_stream(request)
            body_iterator = response.body_iterator

            first_frame = await asyncio.wait_for(body_iterator.__anext__(), timeout=1)
            parsed = json.loads(first_frame.removeprefix("data: ").strip())

            self.assertEqual(parsed["type"], "snapshot")
            self.assertEqual(parsed["status"]["state"], "in_progress")
            self.assertNotIn("transcript", parsed)

            await body_iterator.aclose()

        asyncio.run(scenario())

    def test_keepalive_comment_emitted_when_idle(self):
        async def scenario():
            with mock.patch.object(live_module, "LIVE_KEEPALIVE_SECONDS", 0.05):
                request = _build_stream_request(_hanging_receive())
                response = await live_stream(request)
                body_iterator = response.body_iterator

                await asyncio.wait_for(body_iterator.__anext__(), timeout=1)

                keepalive_frame = await asyncio.wait_for(
                    body_iterator.__anext__(), timeout=1
                )
                self.assertTrue(keepalive_frame.startswith(":"))

                await body_iterator.aclose()

        asyncio.run(scenario())

    def test_disconnected_request_stops_generator_and_unregisters(self):
        async def scenario():
            baseline = live_broadcast_hub.subscriber_count()

            with mock.patch.object(live_module, "LIVE_KEEPALIVE_SECONDS", 0.05):
                request = _build_stream_request(_disconnecting_receive())
                response = await live_stream(request)
                body_iterator = response.body_iterator

                await asyncio.wait_for(body_iterator.__anext__(), timeout=1)

                with self.assertRaises(StopAsyncIteration):
                    await asyncio.wait_for(body_iterator.__anext__(), timeout=1)

            self.assertEqual(live_broadcast_hub.subscriber_count(), baseline)

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
