from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from starlette.responses import StreamingResponse

from app.models.call import utc_now_iso
from app.path_prefix import build_request_app_path
from app.services.live_broadcast import live_broadcast_hub

router = APIRouter()
logger = logging.getLogger(__name__)

LIVE_KEEPALIVE_SECONDS = 15


def format_sse_event(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


LIVE_HTML = """<!DOCTYPE html>
<html lang="fi">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Hotelli Frami | Livekutsun nakyma</title>
  <style>
    :root {
      --bg: #f4efe6;
      --panel: rgba(255, 250, 242, 0.78);
      --panel-strong: rgba(255, 248, 236, 0.94);
      --line: rgba(42, 73, 52, 0.12);
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
      color: #173126;
      font-family: "Trebuchet MS", "Lucida Sans Unicode", sans-serif;
    }

    h1 {
      font-family: Georgia, "Times New Roman", serif;
      font-weight: 700;
    }

    .shell {
      width: min(1200px, calc(100% - 32px));
      margin: 24px auto 40px;
      display: grid;
      gap: 18px;
    }

    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      padding: 24px;
    }

    .conn-rail {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    #conn-dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: var(--success);
      display: inline-block;
    }
  </style>
</head>
<body>
  <main class="shell">
    <div class="conn-rail">
      <span id="conn-dot"></span>
      <span id="conn-label">Yhdistetaan...</span>
    </div>
    <h1>Livekutsun nakyma</h1>
    <section class="panel">
      <h2>Puhelun tila</h2>
      <div id="status-chip">Yhdistetaan live-nakymaan...</div>
    </section>
  </main>
  <script>
    const liveStreamUrl = __API_LIVE_STREAM_URL_JSON__;
    const statusChip = document.getElementById("status-chip");
    const connDot = document.getElementById("conn-dot");
    const connLabel = document.getElementById("conn-label");

    const STATUS_LABELS = {
      ringing: "Puhelu soi",
      connected: "Yhteys avattu",
      in_progress: "Puhelu kaynnissa",
      ended: "Puhelu paattyi",
      error: "Puhelu katkesi virheeseen",
    };

    const STATUS_CLASS = {
      in_progress: "accent",
      ended: "success",
      error: "danger",
    };

    let currentStatus = null;
    let lastFrameAt = Date.now();

    const TRANSIENT_STATES = new Set(["ringing", "connected"]);
    const TRANSIENT_TIMEOUT_MS = 90000;

    function renderStatus(state) {
      if (!state) {
        return;
      }
      currentStatus = state;
      statusChip.textContent = STATUS_LABELS[state] || state;
      statusChip.className = STATUS_CLASS[state] || "";
    }

    function renderIdleFallback() {
      currentStatus = null;
      statusChip.textContent = "Ei aktiivista puhelua juuri nyt";
      statusChip.className = "";
    }

    setInterval(() => {
      if (
        TRANSIENT_STATES.has(currentStatus) &&
        Date.now() - lastFrameAt > TRANSIENT_TIMEOUT_MS
      ) {
        renderIdleFallback();
      }
    }, 5000);

    const source = new EventSource(liveStreamUrl);

    source.onopen = () => {
      connLabel.textContent = "Yhteys muodostettu";
    };

    source.onerror = () => {
      connLabel.textContent = "Yhteys katkesi, yritetaan uudelleen...";
      connDot.style.background = "var(--danger)";
    };

    source.onmessage = (event) => {
      lastFrameAt = Date.now();
      const frame = JSON.parse(event.data);
      if (frame.type === "status") {
        renderStatus(frame.state);
      } else if (frame.type === "snapshot" && frame.status) {
        renderStatus(frame.status.state);
      }
    };
  </script>
</body>
</html>
"""


@router.get("/api/live/stream")
async def live_stream(request: Request) -> StreamingResponse:
    queue = live_broadcast_hub.register()

    async def event_generator():
        try:
            snapshot = {
                "type": "snapshot",
                "ts": utc_now_iso(),
            }
            snapshot.update(live_broadcast_hub.state_snapshot())
            yield format_sse_event(snapshot)

            while True:
                try:
                    event = await asyncio.wait_for(
                        queue.get(), timeout=LIVE_KEEPALIVE_SECONDS
                    )
                except asyncio.TimeoutError:
                    if await request.is_disconnected():
                        break
                    yield ": keepalive\n\n"
                    continue

                if await request.is_disconnected():
                    break
                yield format_sse_event(event)
        except asyncio.CancelledError:
            pass
        finally:
            live_broadcast_hub.unregister(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/live")
async def live_page(request: Request) -> HTMLResponse:
    return HTMLResponse(
        content=_render_live_html(build_request_app_path(request, "/api/live/stream"))
    )


def _render_live_html(api_live_stream_url: str) -> str:
    return LIVE_HTML.replace(
        "__API_LIVE_STREAM_URL_JSON__",
        json.dumps(api_live_stream_url),
    )
