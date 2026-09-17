import inspect
import json
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from starlette.requests import Request

from app.models.call import CallConfig, CallSession
from app.services import realtime_tools, transcript_service
from app.services.dashboard_data import DashboardDataService
from app.services.public_stats import (
    PUBLIC_STATS_FIELDS,
    PUBLIC_STATS_MIN_CALLS,
    build_public_stats,
    reset_public_stats_cache,
)
from app.services.realtime_session import (
    AVAILABILITY_TOOL_NAME,
    CREATE_RESERVATION_TOOL_NAME,
)
from app.services.realtime_tools import execute_realtime_tool


def _write_session_file(
    directory: Path,
    name: str,
    *,
    metadata: dict | None = None,
    duration_seconds=None,
    status: str = "completed",
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": status,
        "duration_seconds": duration_seconds,
        "metadata": metadata or {},
    }
    (directory / f"session_{name}.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


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
        reset_public_stats_cache()
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


class PublicStatsAggregationTests(unittest.TestCase):
    def setUp(self):
        reset_public_stats_cache()
        self.temp_dir = Path("tests") / ".tmp_public_stats_aggregation"
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        reset_public_stats_cache()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_capability_usage_sums_across_records(self):
        for index in range(3):
            _write_session_file(
                self.temp_dir,
                f"r{index}",
                metadata={
                    "capability_invocation_counts": {CREATE_RESERVATION_TOOL_NAME: 2}
                },
            )
        stats = build_public_stats(log_dir=self.temp_dir)
        self.assertEqual(stats["capability_usage"][CREATE_RESERVATION_TOOL_NAME], 6)

    def test_missing_capability_counts_defaults_to_zero_but_counts_total(self):
        _write_session_file(self.temp_dir, "old", metadata={})
        stats = build_public_stats(log_dir=self.temp_dir)
        self.assertEqual(stats["total_calls"], 1)
        self.assertEqual(stats["capability_usage"][AVAILABILITY_TOOL_NAME], 0)

    def test_non_integer_capability_count_contributes_zero(self):
        _write_session_file(
            self.temp_dir,
            "bad",
            metadata={"capability_invocation_counts": {AVAILABILITY_TOOL_NAME: "three"}},
        )
        stats = build_public_stats(log_dir=self.temp_dir)
        self.assertEqual(stats["capability_usage"][AVAILABILITY_TOOL_NAME], 0)
        self.assertEqual(stats["total_calls"], 1)

    def test_reservation_calls_counts_only_true_flagged_records(self):
        _write_session_file(self.temp_dir, "a", metadata={"reservation_created": True})
        _write_session_file(self.temp_dir, "b", metadata={"reservation_created": True})
        _write_session_file(self.temp_dir, "c", metadata={"reservation_created": False})
        _write_session_file(self.temp_dir, "d", metadata={})
        stats = build_public_stats(log_dir=self.temp_dir)
        self.assertEqual(stats["reservation_calls"], 2)

    def test_reservation_calls_falls_back_to_reservation_count_when_flag_absent(self):
        _write_session_file(self.temp_dir, "a", metadata={"reservation_count": 1})
        _write_session_file(self.temp_dir, "b", metadata={"reservation_count": 0})
        stats = build_public_stats(log_dir=self.temp_dir)
        self.assertEqual(stats["reservation_calls"], 1)

    def test_average_duration_excludes_null_but_counts_record(self):
        _write_session_file(self.temp_dir, "a", duration_seconds=10.0)
        _write_session_file(self.temp_dir, "b", duration_seconds=20.0)
        _write_session_file(self.temp_dir, "c", duration_seconds=None)
        stats = build_public_stats(log_dir=self.temp_dir)
        self.assertEqual(stats["average_duration_seconds"], 15.0)
        self.assertEqual(stats["total_calls"], 3)

    def test_average_duration_none_when_no_usable_duration(self):
        _write_session_file(self.temp_dir, "a", duration_seconds=None)
        _write_session_file(self.temp_dir, "b", duration_seconds=None)
        stats = build_public_stats(log_dir=self.temp_dir)
        self.assertIsNone(stats["average_duration_seconds"])
        self.assertEqual(stats["total_calls"], 2)

    def test_errored_call_counted_in_total_calls_no_status_filter(self):
        _write_session_file(self.temp_dir, "err", status="error")
        stats = build_public_stats(log_dir=self.temp_dir)
        self.assertEqual(stats["total_calls"], 1)

    def test_field_set_exact_and_cache_prevents_reread_within_ttl(self):
        _write_session_file(self.temp_dir, "a", duration_seconds=5.0)
        with patch.object(
            DashboardDataService,
            "_read_json",
            wraps=DashboardDataService._read_json,
        ) as mock_read:
            first = build_public_stats(log_dir=self.temp_dir)
            second = build_public_stats(log_dir=self.temp_dir)
        self.assertEqual(set(first), set(PUBLIC_STATS_FIELDS))
        self.assertEqual(set(second), set(PUBLIC_STATS_FIELDS))
        self.assertEqual(mock_read.call_count, 1)

    def test_has_sufficient_sample_false_below_min_calls(self):
        self.assertLess(2, PUBLIC_STATS_MIN_CALLS)
        _write_session_file(self.temp_dir, "a", metadata={"reservation_created": True})
        _write_session_file(self.temp_dir, "b", metadata={"reservation_created": True})
        stats = build_public_stats(log_dir=self.temp_dir)
        self.assertFalse(stats["has_sufficient_sample"])
        self.assertEqual(stats["total_calls"], 2)
        self.assertEqual(stats["reservation_calls"], 2)

    def test_has_sufficient_sample_true_at_min_calls(self):
        for index in range(PUBLIC_STATS_MIN_CALLS):
            _write_session_file(self.temp_dir, f"s{index}")
        stats = build_public_stats(log_dir=self.temp_dir)
        self.assertTrue(stats["has_sufficient_sample"])

    def test_allow_list_projection_exact_for_nonexistent_dir(self):
        reset_public_stats_cache()
        result = build_public_stats(log_dir=self.temp_dir / "does-not-exist")
        self.assertEqual(set(result), set(PUBLIC_STATS_FIELDS))

    def test_module_has_no_reachable_path_into_admin_aggregation_or_live_store(self):
        import app.services.public_stats as module

        source = inspect.getsource(module)
        body = "\n".join(
            line for line in source.splitlines() if not line.lstrip().startswith("#")
        )
        for forbidden in (
            "build_dashboard_payload",
            "dashboard_data_service",
            "DashboardCall",
            "reservation_provider",
            "list_active_reservations",
        ):
            self.assertNotIn(forbidden, body)


if __name__ == "__main__":
    unittest.main()
