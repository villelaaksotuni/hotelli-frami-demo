import asyncio
import json
import os
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from starlette.websockets import WebSocketState

from app.config.settings import Settings, SettingsError
from app.models.call import CallConfig
from app.routes import voice as voice_module
from app.services.runtime_state import InMemoryCallSessionStore


class FakeRequest:
    def __init__(self, method="GET", query_params=None, form_data=None):
        self.method = method
        self.query_params = query_params or {}
        self._form_data = form_data or {}

    async def form(self):
        return self._form_data


def _build_settings(**overrides):
    with patch.dict(os.environ, {}, clear=True):
        base_settings = Settings.from_env()
    base_settings = replace(
        base_settings,
        public_base_url="https://example.test",
        openai_api_key="test-openai-key",
    )
    if overrides:
        base_settings = replace(base_settings, **overrides)
    return base_settings


class FakeOpenAIWebSocket:
    """Stands in for the object returned by `websockets.connect(...)`."""

    def __init__(self):
        self.sent_messages: list[dict] = []
        self.closed = False
        self._stop_event = asyncio.Event()

    async def send(self, message: str) -> None:
        self.sent_messages.append(json.loads(message))

    def __aiter__(self):
        return self

    async def __anext__(self):
        await self._stop_event.wait()
        raise StopAsyncIteration

    async def close(self) -> None:
        self.closed = True
        self._stop_event.set()


class FakeTwilioWebSocket:
    """Stands in for the Twilio-facing `WebSocket` handed to handle_media_stream."""

    def __init__(self, events):
        # events: list of (delay_before_seconds, event_payload_dict)
        self._events = events
        self.client_state = WebSocketState.CONNECTED
        self.sent_json: list[dict] = []
        self.close_call_count = 0

    async def accept(self) -> None:
        pass

    async def iter_text(self):
        for delay_before, payload in self._events:
            if delay_before:
                await asyncio.sleep(delay_before)
            yield json.dumps(payload)
        # Once scripted events are exhausted, park rather than raising
        # StopAsyncIteration, mirroring a call that stays connected.
        while True:
            await asyncio.sleep(3600)

    async def send_json(self, payload: dict) -> None:
        self.sent_json.append(payload)

    async def close(self) -> None:
        self.close_call_count += 1
        self.client_state = WebSocketState.DISCONNECTED


class FakeCallInstance:
    def __init__(self, call_sid: str, recorder: list):
        self._call_sid = call_sid
        self._recorder = recorder

    def update(self, **kwargs):
        self._recorder.append({"call_sid": self._call_sid, **kwargs})
        return self


class FakeTwilioCallsResource:
    def __init__(self, recorder: list):
        self._recorder = recorder

    def __call__(self, call_sid: str) -> FakeCallInstance:
        return FakeCallInstance(call_sid, self._recorder)


class FakeTwilioClient:
    def __init__(self):
        self.update_calls: list[dict] = []
        self.calls = FakeTwilioCallsResource(self.update_calls)


def _with_fake_twilio_client(base_settings, fake_client) -> Settings:
    new_settings = replace(base_settings)
    new_settings.__dict__["twilio_client"] = fake_client
    return new_settings


def _make_fake_connect(fake_openai_ws: FakeOpenAIWebSocket):
    async def _connect(*args, **kwargs):
        return fake_openai_ws

    return _connect


class ConcurrentCallCapTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.store = InMemoryCallSessionStore()
        self.test_settings = _build_settings(max_concurrent_calls=10)

    def _fill_store(self, count: int) -> None:
        for index in range(count):
            self.store.create_outbound_session(
                call_sid=f"CA-existing-{index}",
                config=CallConfig(),
            )

    async def _call(self, call_sid: str = "CA-test"):
        request = FakeRequest(
            method="POST",
            form_data={
                "CallSid": call_sid,
                "From": "+358401111111",
                "To": "+15551234567",
            },
        )
        with patch.object(voice_module, "settings", self.test_settings), patch.object(
            voice_module, "session_store", self.store
        ):
            return await voice_module.handle_incoming_call(request)

    async def test_nine_sessions_still_admits_call(self):
        self._fill_store(9)

        response = await self._call()
        body = response.body.decode()

        self.assertIn("<Connect>", body)
        self.assertIn("<Stream", body)

    async def test_ten_sessions_refuses_call(self):
        self._fill_store(10)

        response = await self._call()
        body = response.body.decode()

        self.assertIn(self.test_settings.capacity_message_fi, body)
        self.assertNotIn("<Connect>", body)
        self.assertNotIn("<Stream", body)

    async def test_refused_call_adds_no_session(self):
        self._fill_store(10)
        count_before = self.store.active_call_count()

        await self._call(call_sid="CA-refused")

        self.assertEqual(self.store.active_call_count(), count_before)
        self.assertIsNone(self.store.get_by_call_sid("CA-refused"))

    async def test_stale_session_reaped_fresh_session_kept(self):
        stale_session = self.store.create_outbound_session(
            call_sid="CA-stale",
            config=CallConfig(),
        )
        stale_age_seconds = self.test_settings.max_call_duration_seconds + 120
        stale_session.created_at = (
            datetime.now(timezone.utc) - timedelta(seconds=stale_age_seconds)
        ).isoformat()

        self.store.create_outbound_session(call_sid="CA-fresh", config=CallConfig())

        await self._call(call_sid="CA-incoming")

        self.assertIsNone(self.store.get_by_call_sid("CA-stale"))
        self.assertIsNotNone(self.store.get_by_call_sid("CA-fresh"))


class SettingsCallLimitDefaultsTests(unittest.TestCase):
    def test_call_limit_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            test_settings = Settings.from_env()

        self.assertEqual(test_settings.max_concurrent_calls, 10)
        self.assertEqual(test_settings.max_call_duration_seconds, 600)
        self.assertEqual(test_settings.wrap_up_warning_seconds, 570)

    def test_invalid_max_concurrent_calls_raises(self):
        for bad_value in ("0", "-1", "ten"):
            with patch.dict(os.environ, {"MAX_CONCURRENT_CALLS": bad_value}, clear=True):
                with self.assertRaises(SettingsError):
                    Settings.from_env()

    def test_invalid_max_call_duration_seconds_raises(self):
        for bad_value in ("0", "-5", "sixty"):
            with patch.dict(
                os.environ, {"MAX_CALL_DURATION_SECONDS": bad_value}, clear=True
            ):
                with self.assertRaises(SettingsError):
                    Settings.from_env()

    def test_invalid_wrap_up_warning_seconds_raises(self):
        for bad_value in ("0", "-30", "soon"):
            with patch.dict(
                os.environ, {"WRAP_UP_WARNING_SECONDS": bad_value}, clear=True
            ):
                with self.assertRaises(SettingsError):
                    Settings.from_env()


class DurationCapTimerTests(unittest.IsolatedAsyncioTestCase):
    async def _run_media_stream(self, fake_twilio_ws, test_settings, fake_openai_ws):
        with patch.object(voice_module, "settings", test_settings), patch.object(
            voice_module.websockets, "connect", _make_fake_connect(fake_openai_ws)
        ):
            return await voice_module.handle_media_stream(fake_twilio_ws)

    async def _run_media_stream_as_background(
        self, fake_twilio_ws, test_settings, fake_openai_ws, run_for_seconds
    ):
        with patch.object(voice_module, "settings", test_settings), patch.object(
            voice_module.websockets, "connect", _make_fake_connect(fake_openai_ws)
        ):
            task = asyncio.create_task(
                voice_module.handle_media_stream(fake_twilio_ws)
            )
            await asyncio.sleep(run_for_seconds)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    def _wrap_up_messages(self, fake_openai_ws, instruction):
        return [
            message
            for message in fake_openai_ws.sent_messages
            if message.get("type") == "response.create"
            and message.get("response", {}).get("instructions") == instruction
        ]

    async def test_wrap_up_timer_sends_exactly_one_response_create(self):
        fake_openai_ws = FakeOpenAIWebSocket()
        fake_twilio_ws = FakeTwilioWebSocket(
            events=[
                (0, {"event": "start", "start": {"streamSid": "MZ1", "callSid": "CA1"}}),
            ]
        )
        test_settings = _build_settings(
            wrap_up_warning_seconds=0.02,
            max_call_duration_seconds=5.0,
        )

        await self._run_media_stream_as_background(
            fake_twilio_ws, test_settings, fake_openai_ws, run_for_seconds=0.08
        )

        wrap_up_messages = self._wrap_up_messages(
            fake_openai_ws, test_settings.wrap_up_instruction_fi
        )
        self.assertEqual(len(wrap_up_messages), 1)

    async def test_cutoff_timer_calls_twilio_update_completed(self):
        fake_openai_ws = FakeOpenAIWebSocket()
        fake_twilio_ws = FakeTwilioWebSocket(
            events=[
                (0, {"event": "start", "start": {"streamSid": "MZ2", "callSid": "CA2"}}),
            ]
        )
        fake_twilio_client = FakeTwilioClient()
        test_settings = _with_fake_twilio_client(
            _build_settings(
                wrap_up_warning_seconds=5.0,
                max_call_duration_seconds=0.02,
            ),
            fake_twilio_client,
        )

        await self._run_media_stream_as_background(
            fake_twilio_ws, test_settings, fake_openai_ws, run_for_seconds=0.08
        )

        self.assertEqual(
            fake_twilio_client.update_calls,
            [{"call_sid": "CA2", "status": "completed"}],
        )

    async def test_cutoff_without_twilio_client_closes_websocket(self):
        fake_openai_ws = FakeOpenAIWebSocket()
        fake_twilio_ws = FakeTwilioWebSocket(
            events=[
                (0, {"event": "start", "start": {"streamSid": "MZ3", "callSid": "CA3"}}),
            ]
        )
        test_settings = _build_settings(
            wrap_up_warning_seconds=5.0,
            max_call_duration_seconds=0.02,
        )
        self.assertIsNone(test_settings.twilio_client)

        await self._run_media_stream_as_background(
            fake_twilio_ws, test_settings, fake_openai_ws, run_for_seconds=0.08
        )

        self.assertGreaterEqual(fake_twilio_ws.close_call_count, 1)

    async def test_warning_delay_gte_cutoff_delay_skips_wrap_up_timer(self):
        fake_openai_ws = FakeOpenAIWebSocket()
        fake_twilio_ws = FakeTwilioWebSocket(
            events=[
                (0, {"event": "start", "start": {"streamSid": "MZ4", "callSid": "CA4"}}),
            ]
        )
        fake_twilio_client = FakeTwilioClient()
        test_settings = _with_fake_twilio_client(
            _build_settings(
                wrap_up_warning_seconds=0.02,
                max_call_duration_seconds=0.02,
            ),
            fake_twilio_client,
        )

        with self.assertLogs(voice_module.logger, level="WARNING") as log_ctx:
            await self._run_media_stream_as_background(
                fake_twilio_ws, test_settings, fake_openai_ws, run_for_seconds=0.08
            )

        self.assertTrue(
            any("skipping wrap-up timer" in message for message in log_ctx.output)
        )
        wrap_up_messages = self._wrap_up_messages(
            fake_openai_ws, test_settings.wrap_up_instruction_fi
        )
        self.assertEqual(wrap_up_messages, [])

    async def test_cancelling_before_deadlines_leaves_fake_clients_untouched(self):
        fake_openai_ws = FakeOpenAIWebSocket()
        fake_twilio_ws = FakeTwilioWebSocket(
            events=[
                (0, {"event": "start", "start": {"streamSid": "MZ5", "callSid": "CA5"}}),
                (0.01, {"event": "stop"}),
            ]
        )
        fake_twilio_client = FakeTwilioClient()
        test_settings = _with_fake_twilio_client(
            _build_settings(
                wrap_up_warning_seconds=0.05,
                max_call_duration_seconds=0.1,
            ),
            fake_twilio_client,
        )

        await asyncio.wait_for(
            self._run_media_stream(fake_twilio_ws, test_settings, fake_openai_ws),
            timeout=2.0,
        )

        wrap_up_messages = self._wrap_up_messages(
            fake_openai_ws, test_settings.wrap_up_instruction_fi
        )
        self.assertEqual(wrap_up_messages, [])
        self.assertEqual(fake_twilio_client.update_calls, [])


class ReadmeCapValuesDriftTests(unittest.TestCase):
    def test_readme_documents_current_cap_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            test_settings = Settings.from_env()

        readme_path = Path(__file__).resolve().parent.parent / "README.md"
        readme_text = readme_path.read_text(encoding="utf-8")

        self.assertIn("## Cost and abuse controls", readme_text)
        self.assertIn(str(test_settings.max_concurrent_calls), readme_text)
        self.assertIn(str(test_settings.max_call_duration_seconds), readme_text)


if __name__ == "__main__":
    unittest.main()
