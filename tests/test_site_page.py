from __future__ import annotations

import asyncio
import dataclasses
import re
import unittest
from unittest.mock import patch

from starlette.requests import Request

from app.config.settings import settings
from app.routes.site import (
    DEMO_DISCLAIMER_FI,
    HOTEL_PAGE_PATH,
    PHONE_NOT_CONFIGURED_FI,
    RESERVE_STEP_FI,
    ROOM_AREAS_FI,
    TEASER_UNITS,
    hotel_page,
)
from app.routes.stats import stats_page
from app.services.sms_utils import normalize_phone
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

    def test_how_it_works_panel_states_three_steps_in_finnish(self):
        self.assertIn("Näin kokeilet demoa", self.body)
        self.assertIn("Soita", self.body)
        self.assertIn('href="/live"', self.body)
        self.assertIn("Live-näkymä", self.body)
        self.assertIn("synteettisen", self.body)
        self.assertIn(RESERVE_STEP_FI, self.body)

    def test_disclaimer_precedes_how_it_works_and_first_teaser(self):
        disclaimer_index = self.body.index(DEMO_DISCLAIMER_FI)
        how_it_works_index = self.body.index("Näin kokeilet demoa")
        first_teaser_unit = TEASER_UNITS[0]
        first_teaser_index = self.body.index(first_teaser_unit.display_name)
        self.assertLess(disclaimer_index, how_it_works_index)
        self.assertLess(disclaimer_index, first_teaser_index)

    def test_phone_number_read_from_settings_not_hardcoded(self):
        settings_a = dataclasses.replace(settings, twilio_phone_number="+358401111111")
        settings_b = dataclasses.replace(settings, twilio_phone_number="+358402222222")

        with patch("app.routes.site.settings", settings_a):
            body_a = asyncio.run(hotel_page(_build_request())).body.decode("utf-8")
        with patch("app.routes.site.settings", settings_b):
            body_b = asyncio.run(hotel_page(_build_request())).body.decode("utf-8")

        number_a = normalize_phone(settings_a.twilio_phone_number)
        number_b = normalize_phone(settings_b.twilio_phone_number)
        self.assertIn(f'href="tel:{number_a}"', body_a)
        self.assertNotIn(number_b, body_a)
        self.assertIn(f'href="tel:{number_b}"', body_b)
        self.assertNotIn(number_a, body_b)

    def test_first_teaser_row_matches_registry_for_first_area(self):
        first_area = ROOM_AREAS_FI[0]
        first_unit = next(unit for unit in UNITS if unit.area == first_area)
        self.assertEqual(first_unit, TEASER_UNITS[0])
        self.assertIn(first_unit.display_name, self.body)
        self.assertIn(f"alkaen {first_unit.nightly_rate_eur} € / yö", self.body)
        self.assertIn(_pluralize_fi(first_unit.capacity, "henkilö", "henkilöä"), self.body)
        self.assertIn(_pluralize_fi(first_unit.min_nights, "yö", "yötä"), self.body)

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

    def test_no_hero_or_brochure_markup_remains(self):
        for forbidden in (
            'class="hero',
            "hero-eyebrow",
            "hero-tagline",
            "room-card-grid",
            "Hyvä tietää",
            "Hintaan sisältyy",
            "Varustelu",
            "Käytännöt",
            "Esteettömyys",
            "Peruutusehdot",
            "Kulkuyhteydet",
        ):
            self.assertNotIn(forbidden, self.body)

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
        self.assertEqual(extra, set())
        root_block_match = re.search(r":root\s*\{(.*?)\}", self.body, re.DOTALL)
        self.assertIsNotNone(root_block_match)
        self.assertIn("@media (max-width: 980px)", self.body)


class TeaserRegistryAndNavConsistencyTests(unittest.TestCase):
    def setUp(self) -> None:
        hotel_response = asyncio.run(hotel_page(_build_request("/")))
        self.hotel_body = hotel_response.body.decode("utf-8")
        stats_response = asyncio.run(stats_page(_build_request("/tilastot")))
        self.stats_body = stats_response.body.decode("utf-8")

    def test_hotel_and_stats_pages_link_to_each_other(self):
        self.assertIn('href="/live"', self.hotel_body)
        self.assertIn('href="/tilastot"', self.hotel_body)
        self.assertIn(f'href="{HOTEL_PAGE_PATH}"', self.stats_body)

    def test_default_language_and_public_pages_declare_finnish(self):
        self.assertEqual(settings.default_language, "fi")
        self.assertIn('lang="fi"', self.hotel_body)
        self.assertIn('lang="fi"', self.stats_body)

    def test_all_teaser_rows_render_matching_registry(self):
        self.assertEqual(len(TEASER_UNITS), len(ROOM_AREAS_FI))
        for area, unit in zip(ROOM_AREAS_FI, TEASER_UNITS):
            self.assertEqual(unit.area, area)
            self.assertIn(unit.display_name, self.hotel_body)
            self.assertIn(f"alkaen {unit.nightly_rate_eur} € / yö", self.hotel_body)
            self.assertIn(
                _pluralize_fi(unit.capacity, "henkilö", "henkilöä"), self.hotel_body
            )
            self.assertIn(
                _pluralize_fi(unit.min_nights, "yö", "yötä"), self.hotel_body
            )

    def test_excluded_units_not_rendered(self):
        excluded = [unit for unit in UNITS if unit not in TEASER_UNITS]
        self.assertTrue(excluded)
        for unit in excluded:
            self.assertNotIn(unit.display_name, self.hotel_body)

    def test_phone_fallback_when_not_configured(self):
        settings_none = dataclasses.replace(settings, twilio_phone_number=None)
        with patch("app.routes.site.settings", settings_none):
            body = asyncio.run(hotel_page(_build_request())).body.decode("utf-8")
        self.assertIn(PHONE_NOT_CONFIGURED_FI, body)
        self.assertNotIn("tel:", body)

    def test_structural_panel_count_and_no_table(self):
        self.assertEqual(self.hotel_body.count('<section class="panel"'), 3)
        self.assertNotIn("<table", self.hotel_body)


if __name__ == "__main__":
    unittest.main()
