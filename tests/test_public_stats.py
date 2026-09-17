import json
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from starlette.requests import Request

from app.models.call import CallConfig, CallSession
from app.services import realtime_tools, transcript_service
from app.services.public_stats import build_public_stats
from app.services.realtime_session import AVAILABILITY_TOOL_NAME
from app.services.realtime_tools import execute_realtime_tool


class FakeAvailabilityResult:
    def to_dict(self):
        return {"status": "available", "confidence": "high"}


class FakeReservationProvider:
    async def check_availability(self, payload):
        return FakeAvailabilityResult()


def _build_stats_page_request() -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": "/tilastot",
            "raw_path": b"/tilastot",
            "root_path": "",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("demo.example.com", 443),
        }
    )


class PublicStatsTracerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = Path("tests") / ".tmp_public_stats"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.fake_provider = FakeReservationProvider()
        self.patcher = patch.object(realtime_tools, "reservation_provider", self.fake_provider)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    async def test_end_to_end_availability_check_reaches_public_stats_page(self):
        session = CallSession(call_sid="CA_stats_test", config=CallConfig())

        result = await execute_realtime_tool(
            AVAILABILITY_TOOL_NAME, "{}", session=session
        )
        self.assertEqual(result["status"], "available")
        self.assertEqual(
            session.metadata["capability_invocation_counts"]["check_availability"], 1
        )

        # Awaiting a second time increments further.
        await execute_realtime_tool(AVAILABILITY_TOOL_NAME, "{}", session=session)
        self.assertEqual(
            session.metadata["capability_invocation_counts"]["check_availability"], 2
        )

        # session=None must not raise and must return the same result shape.
        none_session_result = await execute_realtime_tool(
            AVAILABILITY_TOOL_NAME, "{}", session=None
        )
        self.assertEqual(none_session_result["status"], "available")

        session_record = transcript_service._build_session_record(session, {})
        self.assertEqual(
            session_record["metadata"]["capability_invocation_counts"],
            session.metadata["capability_invocation_counts"],
        )

        session_log_path = self.temp_dir / "session_CA_stats_test.json"
        session_log_path.write_text(
            json.dumps(session_record, ensure_ascii=False), encoding="utf-8"
        )

        stats = build_public_stats(log_dir=self.temp_dir)
        self.assertEqual(stats["total_calls"], 1)
        self.assertEqual(stats["capability_usage"]["check_availability"], 2)

        request = _build_stats_page_request()
        with patch("app.routes.stats.build_public_stats", return_value=stats):
            from app.routes.stats import stats_page

            response = await stats_page(request)

        body = response.body.decode("utf-8")
        self.assertIn("2", body)

    def test_build_public_stats_skips_invalid_json_without_raising(self):
        invalid_path = self.temp_dir / "session_broken.json"
        invalid_path.write_text("not valid json {{{", encoding="utf-8")

        stats = build_public_stats(log_dir=self.temp_dir)
        self.assertEqual(stats["total_calls"], 0)

    def test_build_public_stats_nonexistent_dir_returns_zeroed_result(self):
        nonexistent = self.temp_dir / "does-not-exist"
        stats = build_public_stats(log_dir=nonexistent)
        self.assertEqual(stats["total_calls"], 0)
        self.assertEqual(stats["capability_usage"]["check_availability"], 0)


if __name__ == "__main__":
    unittest.main()
