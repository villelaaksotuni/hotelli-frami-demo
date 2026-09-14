import os
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

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
    base_settings = replace(base_settings, public_base_url="https://example.test")
    if overrides:
        base_settings = replace(base_settings, **overrides)
    return base_settings


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


if __name__ == "__main__":
    unittest.main()
