import asyncio
import re
import unittest
from unittest.mock import patch

from starlette.requests import Request

from app.routes.stats import _format_duration_fi, stats_page
from app.services.public_stats import PUBLIC_CAPABILITY_TOOLS


def _build_request(path: str = "/tilastot") -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": path,
            "raw_path": path.encode("utf-8"),
            "root_path": "",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("demo.example.com", 443),
        }
    )


class StatsPageRenderingTests(unittest.TestCase):
    def _render(self, stats):
        with patch("app.routes.stats.build_public_stats", return_value=stats):
            response = asyncio.run(stats_page(_build_request()))
        self.assertEqual(response.status_code, 200)
        return response.body.decode("utf-8")

    def test_sufficient_sample_shows_all_figures_and_capability_rows(self):
        stats = {
            "total_calls": 12,
            "reservation_calls": 4,
            "average_duration_seconds": 95.0,
            "capability_usage": {
                "check_availability": 20,
                "create_reservation": 4,
                "send_owner_callback_request_sms": 2,
            },
            "has_sufficient_sample": True,
        }
        body = self._render(stats)
        self.assertIn('id="stat-total-calls">12<', body)
        self.assertIn('id="stat-reservation-calls">4<', body)
        self.assertIn("1 min 35 s", body)
        self.assertIn(">20<", body)
        self.assertIn(">2<", body)

    def test_reservation_headline_and_capability_row_use_distinct_labels_when_values_diverge(self):
        stats = {
            "total_calls": 12,
            "reservation_calls": 4,
            "average_duration_seconds": 95.0,
            "capability_usage": {
                "check_availability": 20,
                "create_reservation": 9,
                "send_owner_callback_request_sms": 2,
            },
            "has_sufficient_sample": True,
        }
        body = self._render(stats)
        self.assertIn('id="stat-reservation-calls">4<', body)
        self.assertIn(">9<", body)
        # The confirmed-reservation headline and the raw invocation-attempt row must
        # never share a label — they count different things and can diverge (WR-01).
        headline_index = body.index('id="stat-reservation-calls"')
        headline_label_start = body.rindex('<span class="label">', 0, headline_index)
        headline_label = body[headline_label_start:headline_index]
        capability_row_index = body.index(">9<")
        capability_label_start = body.rindex('<span class="label">', 0, capability_row_index)
        capability_label = body[capability_label_start:capability_row_index]
        self.assertNotEqual(headline_label, capability_label)

    def test_small_sample_shows_exact_totals_and_not_enough_data_elsewhere(self):
        stats = {
            "total_calls": 2,
            "reservation_calls": 1,
            "average_duration_seconds": 42.0,
            "capability_usage": {
                "check_availability": 1,
                "create_reservation": 1,
                "send_owner_callback_request_sms": 0,
            },
            "has_sufficient_sample": False,
        }
        body = self._render(stats)
        self.assertIn('id="stat-total-calls">2<', body)
        self.assertIn('id="stat-reservation-calls">1<', body)
        self.assertIn("Ei vielä riittävästi dataa", body)
        self.assertNotIn("42 s", body)

    def test_empty_log_directory_shows_empty_state_and_200(self):
        stats = {
            "total_calls": 0,
            "reservation_calls": 0,
            "average_duration_seconds": None,
            "capability_usage": {tool: 0 for tool in PUBLIC_CAPABILITY_TOOLS},
            "has_sufficient_sample": False,
        }
        body = self._render(stats)
        self.assertIn("Demosta ei ole vielä kertynyt tilastoja.", body)

    def test_aggregator_exception_shows_empty_state_no_traceback(self):
        with patch(
            "app.routes.stats.build_public_stats",
            side_effect=RuntimeError("boom-secret-path/tmp/leak"),
        ):
            response = asyncio.run(stats_page(_build_request()))
        self.assertEqual(response.status_code, 200)
        body = response.body.decode("utf-8")
        self.assertIn("Demosta ei ole vielä kertynyt tilastoja.", body)
        self.assertNotIn("boom-secret-path", body)
        self.assertNotIn("Traceback", body)

    def test_no_forbidden_per_session_fields_or_masked_number(self):
        stats = {
            "total_calls": 12,
            "reservation_calls": 4,
            "average_duration_seconds": 95.0,
            "capability_usage": {tool: 3 for tool in PUBLIC_CAPABILITY_TOOLS},
            "has_sufficient_sample": True,
        }
        body = self._render(stats)
        for forbidden in (
            "session_id",
            "caller_intent",
            "summary_preview",
            "counterparty",
            "topic_breakdown",
            "recent_calls",
            "transcript",
        ):
            self.assertNotIn(forbidden, body)
        self.assertNotIn("***", body)

    def test_lang_fi_ids_and_finnish_labels_present(self):
        stats = {
            "total_calls": 12,
            "reservation_calls": 4,
            "average_duration_seconds": 95.0,
            "capability_usage": {tool: 3 for tool in PUBLIC_CAPABILITY_TOOLS},
            "has_sufficient_sample": True,
        }
        body = self._render(stats)
        self.assertIn('lang="fi"', body)
        for element_id in (
            "stat-total-calls",
            "stat-reservation-calls",
            "stat-average-duration",
            "capability-usage",
        ):
            self.assertIn(f'id="{element_id}"', body)
        for label in ("Puheluita yhteensä", "Tehtyjä demovarauksia", "Puhelun keskikesto"):
            self.assertIn(label, body)

    def test_palette_subset_and_breakpoint_and_no_inner_html(self):
        stats = {
            "total_calls": 12,
            "reservation_calls": 4,
            "average_duration_seconds": 95.0,
            "capability_usage": {tool: 3 for tool in PUBLIC_CAPABILITY_TOOLS},
            "has_sufficient_sample": True,
        }
        body = self._render(stats)
        hex_colors = set(re.findall(r"#[0-9a-fA-F]{6}\b", body))
        allowed_hex = {"#f4efe6", "#b85c38", "#8a2f2b", "#2f6f50", "#173126"}
        self.assertTrue(hex_colors.issubset(allowed_hex), hex_colors - allowed_hex)
        self.assertIn("@media (max-width: 980px)", body)
        self.assertNotIn(".innerHTML =", body)


class FormatDurationFiTests(unittest.TestCase):
    def test_seconds_only_under_a_minute(self):
        self.assertEqual(_format_duration_fi(45.0), "45 s")

    def test_minutes_and_seconds_at_or_above_a_minute(self):
        self.assertEqual(_format_duration_fi(125.0), "2 min 5 s")

    def test_none_renders_not_enough_data_string(self):
        self.assertEqual(_format_duration_fi(None), "Ei vielä riittävästi dataa")


if __name__ == "__main__":
    unittest.main()
