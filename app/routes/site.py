from __future__ import annotations

import html

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.config.settings import settings
from app.models.reservation import Unit
from app.path_prefix import build_request_app_path
from app.services.sms_utils import normalize_phone
from app.services.unit_registry import UNITS

router = APIRouter()

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
        phone_step_html = html.escape(PHONE_NOT_CONFIGURED_FI, quote=True)

    escaped_live_link = html.escape(live_link, quote=True)
    live_step_html = (
        f'Avaa <a href="{escaped_live_link}">Live-näkymä</a> ja seuraa puhelua '
        "reaaliajassa."
    )

    return (
        '<section class="section-divider" id="how-it-works">'
        f"<h2>{html.escape(HOW_IT_WORKS_HEADING_FI, quote=True)}</h2>"
        f"<p>{html.escape(HOW_IT_WORKS_INTRO_FI, quote=True)}</p>"
        "<ol>"
        f"<li>{phone_step_html}</li>"
        f"<li>{live_step_html}</li>"
        f"<li>{html.escape(RESERVE_STEP_FI, quote=True)}</li>"
        "</ol>"
        "</section>"
    )


def _render_room_teaser_row_html(unit: Unit) -> str:
    display_name = html.escape(unit.display_name, quote=True)
    area_text = html.escape(unit.area, quote=True)
    rate_text = html.escape(f"{unit.nightly_rate_eur} € / yö", quote=True)
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


def _first_unit_in_area(area: str) -> Unit:
    for unit in UNITS:
        if unit.area == area:
            return unit
    raise ValueError(f"unit_registry.UNITS has no unit in area {area!r}")


TEASER_UNITS: tuple[Unit, ...] = tuple(_first_unit_in_area(area) for area in ROOM_AREAS_FI)


def _render_room_teasers_html() -> str:
    rows_html = "".join(_render_room_teaser_row_html(unit) for unit in TEASER_UNITS)
    return (
        '<section class="section-divider" id="room-teasers">'
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
      --accent-gold: #6b5327;
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
      font-size: 44px;
      line-height: 1.2;
      letter-spacing: -0.015em;
    }

    h2 {
      font-size: 24px;
      line-height: 1.3;
      letter-spacing: 0.01em;
    }

    .label {
      font-size: 12px;
      font-weight: 600;
      line-height: 1.4;
      color: var(--accent-gold);
      text-transform: uppercase;
      letter-spacing: 0.09em;
    }

    .shell {
      width: min(1200px, calc(100% - 32px));
      margin: 24px auto 48px;
      display: grid;
      gap: 56px;
    }

    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      padding: 24px;
    }

    #demo-disclaimer {
      background: var(--panel-strong);
      border: 1px solid var(--accent-gold);
      font-weight: 600;
    }

    .section-divider {
      border-top: 1px solid var(--line);
      padding-top: 40px;
    }

    .top-nav {
      display: flex;
      gap: 24px;
    }

    .top-nav a {
      color: var(--accent-gold);
      font-weight: 700;
      text-decoration: none;
      text-transform: uppercase;
      letter-spacing: 0.09em;
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
      padding: 20px 0;
      border-bottom: 1px solid var(--line);
    }

    .room-teaser-row:last-child {
      border-bottom: none;
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

      .section-divider {
        padding-top: 28px;
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
