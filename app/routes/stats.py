from __future__ import annotations

import html
import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.path_prefix import build_request_app_path
from app.routes.site import HOTEL_PAGE_PATH, TOKENS_CSS_PATH
from app.services.public_stats import PUBLIC_CAPABILITY_TOOLS, build_public_stats
from app.services.realtime_session import (
    AVAILABILITY_TOOL_NAME,
    CALLBACK_REQUEST_SMS_TOOL_NAME,
    CREATE_RESERVATION_TOOL_NAME,
)

router = APIRouter()
logger = logging.getLogger(__name__)

NOT_ENOUGH_DATA_FI = "Ei vielä riittävästi dataa"
EMPTY_STATE_HEADING_FI = "Demosta ei ole vielä kertynyt tilastoja."
EMPTY_STATE_BODY_FI = (
    "Heti kun demoon soitetaan ensimmäinen puhelu, sen tilastot näkyvät tässä."
)

CAPABILITY_USAGE_LABELS_FI: dict[str, str] = {
    AVAILABILITY_TOOL_NAME: "Saatavuuden tarkistukset",
    CREATE_RESERVATION_TOOL_NAME: "Varausyrityksiä",
    CALLBACK_REQUEST_SMS_TOOL_NAME: "Yhteydenottopyyntöjä",
}


def _format_duration_fi(seconds: float | None) -> str:
    if seconds is None:
        return NOT_ENOUGH_DATA_FI
    total_seconds = int(round(seconds))
    if total_seconds < 60:
        return f"{total_seconds} s"
    minutes, remainder_seconds = divmod(total_seconds, 60)
    return f"{minutes} min {remainder_seconds} s"


STATS_HTML = """<!DOCTYPE html>
<html lang="fi">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Hotelli Frami | Demon tilastot</title>
  <link rel="stylesheet" href="__TOKENS_LINK__" />
  <style>
    :root {
      --bg: var(--beige, #f4efe6);
      --panel: rgba(255, 250, 242, 0.78);
      --panel-strong: rgba(255, 248, 236, 0.94);
      --line: color-mix(in srgb, var(--primary-900, #173126) 18%, transparent);
      --ink: var(--primary-900, #173126);
      --accent: var(--golden-500, #b85c38);
      --danger: #8a2f2b;
      --success: #2f6f50;
      --radius: 2px;
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      min-height: 100vh;
      background: var(--bg);
      color: var(--ink);
      font-family: var(--font-sans, "Helvetica Neue", Arial, sans-serif);
      font-size: 16px;
      font-weight: 300;
      line-height: 1.6;
      -webkit-font-smoothing: antialiased;
    }

    .skip-link {
      position: fixed;
      z-index: 10;
      top: 1rem;
      left: 1rem;
      padding: 0.75rem 1rem;
      background: var(--ink);
      color: var(--white, white);
      transform: translateY(-180%);
    }

    .skip-link:focus { transform: translateY(0); }

    :focus-visible {
      outline: 2px solid var(--ink);
      outline-offset: 4px;
    }

    h1, h2 { margin: 0; font-weight: 400; }

    h1 {
      font-size: clamp(2.75rem, 8vw, 6.5rem);
      letter-spacing: -0.05em;
      line-height: 0.95;
    }

    h2 {
      margin-bottom: 1.25rem;
      font-size: clamp(1.4rem, 3vw, 2.25rem);
      letter-spacing: -0.025em;
      line-height: 1.15;
    }

    .label {
      font-size: 13px;
      font-weight: 400;
      line-height: 1.4;
      color: var(--ink);
    }

    .shell {
      width: min(1200px, calc(100% - (2 * var(--page-gutter, 1.5rem))));
      margin: 0 auto;
      padding: clamp(2rem, 6vw, 5rem) 0;
      display: grid;
      gap: clamp(1.5rem, 3vw, 2.5rem);
    }

    .panel {
      background: color-mix(in srgb, var(--beigeDark, #f4efe6) 58%, white);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      padding: clamp(1.25rem, 3vw, 2rem);
    }

    .top-nav {
      display: flex;
      flex-wrap: wrap;
      gap: 1.5rem;
      padding-bottom: 1.25rem;
      border-bottom: 1px solid var(--line);
    }

    .top-nav a {
      color: var(--ink);
      font-size: 0.8rem;
      font-weight: 600;
      letter-spacing: 0.1em;
      text-underline-offset: 0.25em;
      text-transform: uppercase;
    }

    .stats-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 24px;
    }

    .stat-figure {
      display: grid;
      gap: 8px;
    }

    .stat-value {
      font-size: clamp(2rem, 5vw, 3.75rem);
      font-weight: 400;
      color: var(--ink);
    }

    #capability-usage {
      display: grid;
      gap: 12px;
    }

    .capability-row {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      padding: 12px 16px;
      border: 1px solid var(--line);
      border-radius: 16px;
    }

    .state-heading {
      margin: 0 0 8px;
      font-weight: 700;
    }

    .state-body {
      margin: 0;
    }

    @media (max-width: 980px) {
      .stats-grid {
        grid-template-columns: 1fr;
      }
    }

    @media (prefers-reduced-motion: reduce) {
      *, *::before, *::after { transition-duration: 0.01ms !important; }
    }
  </style>
</head>
<body>
  <a class="skip-link" href="#main-content">Siirry pääsisältöön</a>
  <main class="shell" id="main-content">
    <nav class="top-nav" aria-label="Päänavigaatio"><a href="__HOTEL_LINK__">Hotelli Frami</a> <a href="__LIVE_LINK__">Live-näkymä</a></nav>
    <h1>Demon tilastot</h1>
    <section class="panel">
      <p>Tämä sivu näyttää vain kaikkien demopuheluiden yhteenlasketut kokonaisluvut. Yksittäisiä puheluita, soittajia tai puheluiden sisältöä ei näytetä eikä niitä ole mahdollista hakea tästä näkymästä.</p>
    </section>
    __CONTENT_HTML__
    <footer class="panel">
      <p class="label">Luvut ovat kertyneet koko demon elinkaaren ajalta ja lasketaan uudelleen jokaisella sivun latauksella.</p>
    </footer>
  </main>
</body>
</html>
"""


def _render_empty_state_html() -> str:
    return (
        '<section class="panel">'
        f'<p class="state-heading">{html.escape(EMPTY_STATE_HEADING_FI, quote=True)}</p>'
        f'<p class="state-body">{html.escape(EMPTY_STATE_BODY_FI, quote=True)}</p>'
        "</section>"
    )


def _render_capability_row_html(tool: str, count: int | None) -> str:
    label = CAPABILITY_USAGE_LABELS_FI.get(tool, tool)
    value_text = NOT_ENOUGH_DATA_FI if count is None else str(count)
    return (
        '<div class="capability-row">'
        f'<span class="capability-label">{html.escape(label, quote=True)}</span>'
        f'<span class="capability-value">{html.escape(value_text, quote=True)}</span>'
        "</div>"
    )


def _render_stats_content_html(stats: dict[str, Any]) -> str:
    total_calls = int(stats.get("total_calls") or 0)
    reservation_calls = int(stats.get("reservation_calls") or 0)
    has_sufficient_sample = bool(stats.get("has_sufficient_sample"))
    average_duration_seconds = stats.get("average_duration_seconds")
    capability_usage = stats.get("capability_usage") or {}

    average_duration_text = (
        _format_duration_fi(average_duration_seconds)
        if has_sufficient_sample
        else NOT_ENOUGH_DATA_FI
    )

    capability_rows_html = "".join(
        _render_capability_row_html(
            tool,
            capability_usage.get(tool, 0) if has_sufficient_sample else None,
        )
        for tool in PUBLIC_CAPABILITY_TOOLS
    )

    return (
        '<section class="panel stats-grid">'
        '<div class="stat-figure">'
        '<span class="label">Puheluita yhteensä</span>'
        f'<span class="stat-value" id="stat-total-calls">{html.escape(str(total_calls), quote=True)}</span>'
        "</div>"
        '<div class="stat-figure">'
        '<span class="label">Tehtyjä demovarauksia</span>'
        f'<span class="stat-value" id="stat-reservation-calls">{html.escape(str(reservation_calls), quote=True)}</span>'
        "</div>"
        '<div class="stat-figure">'
        '<span class="label">Puhelun keskikesto</span>'
        f'<span class="stat-value" id="stat-average-duration">{html.escape(average_duration_text, quote=True)}</span>'
        "</div>"
        "</section>"
        '<section class="panel">'
        "<h2>Kokeiltujen ominaisuuksien käyttö</h2>"
        f'<div id="capability-usage">{capability_rows_html}</div>'
        "</section>"
    )


def _render_stats_html(*, request: Request, stats: dict[str, Any] | None) -> str:
    live_link = build_request_app_path(request, "/live")
    hotel_link = build_request_app_path(request, HOTEL_PAGE_PATH)
    tokens_link = build_request_app_path(request, TOKENS_CSS_PATH)

    if stats is None or int(stats.get("total_calls") or 0) == 0:
        content_html = _render_empty_state_html()
    else:
        content_html = _render_stats_content_html(stats)

    return (
        STATS_HTML.replace("__LIVE_LINK__", html.escape(live_link, quote=True))
        .replace("__HOTEL_LINK__", html.escape(hotel_link, quote=True))
        .replace("__TOKENS_LINK__", html.escape(tokens_link, quote=True))
        .replace("__CONTENT_HTML__", content_html)
    )


@router.get("/tilastot")
async def stats_page(request: Request) -> HTMLResponse:
    try:
        stats = build_public_stats()
    except Exception:
        logger.warning("Failed to build public stats; rendering empty state", exc_info=True)
        stats = None

    return HTMLResponse(content=_render_stats_html(request=request, stats=stats))
