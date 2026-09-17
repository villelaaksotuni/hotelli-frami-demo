from __future__ import annotations

import html
import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.config.settings import settings
from app.path_prefix import build_request_app_path
from app.services.sms_utils import normalize_phone
from app.services.unit_registry import UNITS

router = APIRouter()
logger = logging.getLogger(__name__)

HOTEL_PAGE_PATH = "/"

DEMO_DISCLAIMER_FI = (
    "Hotelli Frami on kuvitteellinen hotelli. Tämä sivu on osa tekoälyavustajan "
    "julkista demoa: kohteet, hinnat ja yhteystiedot ovat keksittyjä, eikä täältä "
    "voi tehdä oikeaa varausta."
)

ROOM_AREAS_FI = ("Framinranta", "Jokipuisto", "Kampusaukio")

HOW_IT_WORKS_HEADING_FI = "Näin kokeilet demoa"
HOW_IT_WORKS_INTRO_FI = (
    "Hotelli Frami on tekoälyavustajan puhelindemo. Soita alla näkyvään numeroon "
    "ja keskustele aidon tekoälyagentin kanssa suomeksi – voit pyytää huonetta ja "
    "kokeilla varauksen tekemistä puhelun aikana."
)
PHONE_NOT_CONFIGURED_FI = "Demon puhelinnumero ei ole juuri nyt käytössä."
RESERVE_STEP_FI = (
    "Kerro avustajalle, minkä huoneen haluaisit varata – se tarkistaa saatavuuden "
    "ja tekee synteettisen eli ei-oikean varauksen suoraan puhelun aikana."
)
TEASER_HEADING_FI = "Kokeile pyytää jotain näistä huoneista"
TEASER_INTRO_FI = (
    "Nämä ovat esimerkkejä huoneista, joita voit pyytää avustajalta puhelun aikana."
)


def _pluralize_fi(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


def _render_how_it_works_html(request: Request) -> str:
    live_link = build_request_app_path(request, "/live")
    normalized_phone = normalize_phone(settings.twilio_phone_number)

    if normalized_phone:
        escaped_phone = html.escape(normalized_phone, quote=True)
        phone_step_html = (
            f'Soita numeroon <a href="tel:{escaped_phone}">{escaped_phone}</a>.'
        )
    else:
        phone_step_html = PHONE_NOT_CONFIGURED_FI

    escaped_live_link = html.escape(live_link, quote=True)
    live_step_html = (
        f'Avaa <a href="{escaped_live_link}">Live-näkymä</a> ja seuraa puhelua '
        "reaaliajassa."
    )

    return (
        '<section class="panel" id="how-it-works">'
        f"<h2>{HOW_IT_WORKS_HEADING_FI}</h2>"
        f"<p>{HOW_IT_WORKS_INTRO_FI}</p>"
        "<ol>"
        f"<li>{phone_step_html}</li>"
        f"<li>{live_step_html}</li>"
        f"<li>{RESERVE_STEP_FI}</li>"
        "</ol>"
        "</section>"
    )


def _render_room_teaser_row_html(unit) -> str:
    display_name = html.escape(unit.display_name, quote=True)
    area_text = html.escape(unit.area, quote=True)
    rate_text = html.escape(f"alkaen {unit.nightly_rate_eur} € / yö", quote=True)
    capacity_text = html.escape(
        f"enintään {_pluralize_fi(unit.capacity, 'henkilö', 'henkilöä')}",
        quote=True,
    )
    nights_text = html.escape(
        f"vähintään {_pluralize_fi(unit.min_nights, 'yö', 'yötä')}",
        quote=True,
    )
    return (
        '<div class="room-teaser-row">'
        "<div>"
        f'<p class="room-card-title">{display_name}</p>'
        f'<p class="label">{area_text}</p>'
        "</div>"
        "<div>"
        f'<p class="room-card-detail">{rate_text}</p>'
        f'<p class="room-card-detail">{capacity_text}</p>'
        f'<p class="room-card-detail">{nights_text}</p>'
        "</div>"
        "</div>"
    )


TEASER_UNITS: tuple = tuple(
    next(unit for unit in UNITS if unit.area == area) for area in ROOM_AREAS_FI
)


def _render_room_teasers_html() -> str:
    rows_html = "".join(_render_room_teaser_row_html(unit) for unit in TEASER_UNITS)
    return (
        '<section class="panel" id="room-teasers">'
        f"<h2>{TEASER_HEADING_FI}</h2>"
        f"<p>{TEASER_INTRO_FI}</p>"
        f'<div class="room-teaser-list">{rows_html}</div>'
        "</section>"
    )


HOTEL_HTML = """<!DOCTYPE html>
<html lang="fi">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Hotelli Frami</title>
  <style>
    :root {
      --bg: #f4efe6;
      --panel: rgba(255, 250, 242, 0.78);
      --panel-strong: rgba(255, 248, 236, 0.94);
      --line: rgba(42, 73, 52, 0.12);
      --ink: #173126;
      --accent: #b85c38;
      --danger: #8a2f2b;
      --success: #2f6f50;
      --radius: 24px;
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      min-height: 100vh;
      background: var(--bg);
      color: var(--ink);
      font-family: "Trebuchet MS", "Lucida Sans Unicode", sans-serif;
      font-size: 16px;
      font-weight: 400;
      line-height: 1.5;
    }

    h1, h2 {
      font-family: Georgia, "Times New Roman", serif;
      font-weight: 700;
      margin: 0 0 16px;
    }

    h1 {
      font-size: 28px;
      line-height: 1.15;
    }

    h2 {
      font-size: 20px;
      line-height: 1.2;
    }

    .label {
      font-size: 13px;
      font-weight: 400;
      line-height: 1.4;
      color: var(--ink);
    }

    .shell {
      width: min(1200px, calc(100% - 32px));
      margin: 24px auto 48px;
      display: grid;
      gap: 24px;
    }

    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      padding: 24px;
    }

    .top-nav {
      display: flex;
      gap: 24px;
    }

    .top-nav a {
      color: var(--accent);
      font-weight: 700;
      text-decoration: none;
    }

    ol, ul {
      margin: 0;
      padding-left: 20px;
    }

    li {
      margin-bottom: 8px;
    }

    .room-teaser-list {
      display: grid;
      gap: 12px;
    }

    .room-teaser-row {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      padding: 12px 16px;
      border: 1px solid var(--line);
      border-radius: 16px;
    }

    .room-card-title {
      margin: 0 0 4px;
      font-weight: 700;
    }

    .room-card-detail {
      margin: 0;
      font-size: 14px;
    }

    @media (max-width: 980px) {
      .panel {
        padding: 20px;
      }

      .room-teaser-row {
        flex-direction: column;
      }
    }
  </style>
</head>
<body>
  <main class="shell">
    <nav class="top-nav">
      <a href="__STATS_LINK__">Demon tilastot</a>
      <a href="__LIVE_LINK__">Live-näkymä</a>
    </nav>
    <h1>Hotelli Frami</h1>
    <section class="panel" id="demo-disclaimer">
      <p>__DEMO_DISCLAIMER_FI__</p>
    </section>
    __HOW_IT_WORKS_HTML__
    __ROOM_TEASERS_HTML__
  </main>
</body>
</html>
"""


def _render_hotel_html(request: Request) -> str:
    live_link = build_request_app_path(request, "/live")
    stats_link = build_request_app_path(request, "/tilastot")
    return (
        HOTEL_HTML.replace("__DEMO_DISCLAIMER_FI__", DEMO_DISCLAIMER_FI)
        .replace("__HOW_IT_WORKS_HTML__", _render_how_it_works_html(request))
        .replace("__ROOM_TEASERS_HTML__", _render_room_teasers_html())
        .replace("__LIVE_LINK__", html.escape(live_link, quote=True))
        .replace("__STATS_LINK__", html.escape(stats_link, quote=True))
    )


@router.get(HOTEL_PAGE_PATH)
async def hotel_page(request: Request) -> HTMLResponse:
    return HTMLResponse(content=_render_hotel_html(request))
