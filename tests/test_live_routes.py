import asyncio
import unittest

from starlette.requests import Request

from app.routes.live import live_page


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


class LiveRoutesTests(unittest.TestCase):
    def setUp(self):
        response = asyncio.run(live_page(_build_page_request()))
        self.body = response.body.decode("utf-8")

    def test_all_region_element_ids_present(self):
        for element_id in (
            "conn-dot",
            "status-chip",
            "transcript-list",
            "transcript-scroll-lock",
            "agent-state",
            "capability-list",
            "board-list",
        ):
            self.assertIn(f'id="{element_id}"', self.body)

    def test_shared_call_panel_idle_and_board_idle_copy_present(self):
        self.assertIn("Ei aktiivista puhelua juuri nyt", self.body)
        self.assertIn("Ei viela demovarauksia", self.body)

    def test_loading_and_disconnect_copy_present(self):
        self.assertIn("Yhdistetaan live-nakymaan", self.body)
        self.assertIn("Yhteys katkesi hetkeksi", self.body)

    def test_palette_matches_dashboard_and_introduces_no_new_hex(self):
        for value in (
            "#f4efe6",
            "#b85c38",
            "#8a2f2b",
            "#2f6f50",
            "rgba(255, 250, 242, 0.78)",
        ):
            self.assertIn(value, self.body)

        import re

        hex_colors = set(re.findall(r"#[0-9a-fA-F]{6}\b", self.body))
        allowed_hex = {"#f4efe6", "#b85c38", "#8a2f2b", "#2f6f50", "#173126"}
        self.assertTrue(hex_colors.issubset(allowed_hex), hex_colors - allowed_hex)

    def test_escape_html_present_and_no_inner_html_assignment(self):
        self.assertIn("escapeHtml", self.body)
        self.assertNotIn(".innerHTML =", self.body)

    def test_scroll_lock_has_visible_text_or_aria_label(self):
        import re

        match = re.search(
            r'<button[^>]*id="transcript-scroll-lock"[^>]*>(.*?)</button>',
            self.body,
            re.DOTALL,
        )
        self.assertIsNotNone(match)
        has_aria_label = 'aria-label="' in match.group(0)
        has_visible_text = match.group(1).strip() != ""
        self.assertTrue(has_aria_label or has_visible_text)

    def test_page_declares_finnish_lang(self):
        self.assertIn('lang="fi"', self.body)

    def test_980px_breakpoint_present(self):
        self.assertIn("@media (max-width: 980px)", self.body)


if __name__ == "__main__":
    unittest.main()
