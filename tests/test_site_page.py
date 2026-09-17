from __future__ import annotations

import asyncio
import re
import unittest

from starlette.requests import Request

from app.routes.site import DEMO_DISCLAIMER_FI, HOTEL_PAGE_PATH, hotel_page
from app.services.unit_registry import UNITS


def _build_request(path: str = "/") -> Request:
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


def _pluralize_fi(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


class HotelPageRenderingTests(unittest.TestCase):
    def setUp(self) -> None:
        response = asyncio.run(hotel_page(_build_request()))
        self.assertEqual(response.status_code, 200)
        self.body = response.body.decode("utf-8")

    def test_every_unit_display_name_present_and_card_count_matches_units(self):
        for unit in UNITS:
            self.assertIn(unit.display_name, self.body)
        card_titles = re.findall(r'class="room-card-title">([^<]+)<', self.body)
        self.assertEqual(len(card_titles), len(UNITS))

    def test_each_unit_rate_capacity_and_min_nights_render_and_group_by_area(self):
        for unit in UNITS:
            self.assertIn(f"{unit.nightly_rate_eur} €", self.body)
            self.assertIn(_pluralize_fi(unit.capacity, "henkilö", "henkilöä"), self.body)
            self.assertIn(_pluralize_fi(unit.min_nights, "yö", "yötä"), self.body)
        for area in ("Framinranta", "Jokipuisto", "Kampusaukio"):
            self.assertIn(f">{area}<", self.body)

    def test_disclaimer_precedes_room_names_and_price_content(self):
        disclaimer_index = self.body.index(DEMO_DISCLAIMER_FI)
        first_unit_index = self.body.index(UNITS[0].display_name)
        first_euro_index = self.body.index("€")
        self.assertLess(disclaimer_index, first_unit_index)
        self.assertLess(disclaimer_index, first_euro_index)

    def test_disclaimer_markup_not_hidden_or_collapsible(self):
        disclaimer_index = self.body.index(DEMO_DISCLAIMER_FI)
        surrounding = self.body[max(0, disclaimer_index - 400) : disclaimer_index + 100]
        for forbidden in (
            "hidden",
            "display:none",
            "display: none",
            "opacity:0",
            "opacity: 0",
            "opacity: 0;",
            "visibility:hidden",
            "visibility: hidden",
            "<details",
            "<summary",
        ):
            self.assertNotIn(forbidden, surrounding)

    def test_no_transaction_or_lead_capture_affordance(self):
        lowered = self.body.lower()
        for forbidden in (
            "<form",
            "<input",
            "<button",
            'type="submit"',
            "varaa nyt",
            "book now",
            "maksa nyt",
            "newsletter",
            "uutiskirje",
        ):
            self.assertNotIn(forbidden, lowered)

    def test_canon_facts_render_verbatim(self):
        for fact in (
            "klo 15:00",
            "klo 11:00",
            "liinavaatteet ja pyyhkeet",
            "loppusiivous",
            "WiFi",
            "ilmainen pysäköinti",
            "24,00 €",
            "Lemmikit eivät ole sallittuja missään kohteessa.",
            "Kaikki kohteet ovat savuttomia.",
            "Huoneistohotelli Framinranta on esteetön.",
            "FramiCharge",
            "Kesäsesonki",
            "Sesongin ulkopuolella",
            "Tapahtuma-ajat",
            "No-show",
            "Veloitetaan 100 %",
            "Kampusaukion huoneistot",
            "Framinrannan keskustan kohteet",
            "Jokipuiston huoneistot",
        ):
            self.assertIn(fact, self.body)

    def test_declares_finnish_lang(self):
        self.assertIn('lang="fi"', self.body)

    def test_links_to_live_and_stats(self):
        self.assertIn('href="/live"', self.body)
        self.assertIn('href="/tilastot"', self.body)

    def test_route_mounted_once_with_no_dependencies(self):
        from app.main import app

        matches = [r for r in app.routes if getattr(r, "path", None) == HOTEL_PAGE_PATH]
        self.assertEqual(len(matches), 1, matches)
        self.assertEqual(matches[0].dependant.dependencies, [])

    def test_palette_subset_and_breakpoint(self):
        hex_colors = set(re.findall(r"#[0-9a-fA-F]{6}\b", self.body))
        allowed_hex = {"#f4efe6", "#b85c38", "#8a2f2b", "#2f6f50", "#173126"}
        extra = hex_colors - allowed_hex
        self.assertLessEqual(len(extra), 2, extra)
        root_block_match = re.search(r":root\s*\{(.*?)\}", self.body, re.DOTALL)
        self.assertIsNotNone(root_block_match)
        root_block = root_block_match.group(1)
        for extra_color in extra:
            self.assertIn(extra_color, root_block)
        self.assertIn("@media (max-width: 980px)", self.body)


if __name__ == "__main__":
    unittest.main()
