from __future__ import annotations

import html
import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.services.public_stats import build_public_stats

router = APIRouter()
logger = logging.getLogger(__name__)


STATS_HTML = """<!DOCTYPE html>
<html lang="fi">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Hotelli Frami | Demon tilastot</title>
</head>
<body>
  <h1>Demon tilastot</h1>
  <p>Puheluita yhteensa: __TOTAL_CALLS__</p>
  <p>Saatavuuden tarkistukset: __AVAILABILITY_COUNT__</p>
</body>
</html>
"""


def _render_stats_html(*, total_calls: int, availability_count: int) -> str:
    return STATS_HTML.replace(
        "__TOTAL_CALLS__", html.escape(str(total_calls), quote=True)
    ).replace(
        "__AVAILABILITY_COUNT__", html.escape(str(availability_count), quote=True)
    )


@router.get("/tilastot")
async def stats_page(request: Request) -> HTMLResponse:
    stats = build_public_stats()
    total_calls = int(stats.get("total_calls") or 0)
    availability_count = int(stats.get("capability_usage", {}).get("check_availability") or 0)
    return HTMLResponse(
        content=_render_stats_html(
            total_calls=total_calls, availability_count=availability_count
        )
    )
