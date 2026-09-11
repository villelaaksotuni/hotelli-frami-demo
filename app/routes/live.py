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

    #conn-detail {
      margin: 4px 0 0;
    }

    .live-grid {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      gap: 24px;
    }

    .live-col {
      display: grid;
      gap: 24px;
      align-content: start;
    }

    .transcript-panel {
      min-height: 420px;
      display: grid;
      gap: 16px;
      align-content: start;
    }

    .section-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 8px;
      margin-bottom: 16px;
    }

    .section-header h2 {
      margin: 0;
    }

    #transcript-scroll-lock {
      min-width: 44px;
      min-height: 44px;
      padding: 8px 16px;
      border-radius: var(--radius);
      border: 1px solid var(--line);
      background: var(--panel-strong);
      color: var(--ink);
      font-family: inherit;
      font-size: 13px;
      cursor: not-allowed;
    }

    .board-panel {
      width: 100%;
    }

    .state-heading {
      margin: 0 0 8px;
      font-weight: 700;
    }

    .state-body {
      margin: 0;
    }

    @media (max-width: 980px) {
      .live-grid {
        grid-template-columns: 1fr;
      }
    }
  </style>
</head>
<body>
  <main class="shell">
    <div class="conn-rail" id="conn-rail">
      <span id="conn-dot"></span>
      <div>
        <span id="conn-label">Yhdistetaan...</span>
        <p id="conn-detail" class="label"></p>
      </div>
    </div>
    <h1>Livekutsun nakyma</h1>
    <div class="live-grid">
      <div class="live-col">
        <section class="panel call-panel" id="panel-status">
          <h2>Puhelun tila</h2>
          <div id="status-chip">Yhdistetaan live-nakymaan...</div>
        </section>
        <section class="panel call-panel transcript-panel" id="panel-transcript">
          <div class="section-header">
            <h2>Litteraatti</h2>
            <button
              id="transcript-scroll-lock"
              type="button"
              disabled
              aria-label="Lukitse vieritys viimeisimpaan viestiin"
            >Lukitse alimpaan</button>
          </div>
          <div id="transcript-list">Yhdistetaan live-nakymaan...</div>
        </section>
      </div>
      <div class="live-col">
        <section class="panel call-panel" id="panel-agent">
          <h2>Agentin nakyma</h2>
          <div id="agent-state">Yhdistetaan live-nakymaan...</div>
        </section>
        <section class="panel call-panel" id="panel-capability">
          <h2>Kokeile itse</h2>
          <div id="capability-list">Yhdistetaan live-nakymaan...</div>
        </section>
      </div>
    </div>
    <section class="panel board-panel" id="panel-board">
      <h2>Varaustaulu</h2>
      <div id="board-list">
        <p class="state-heading">Ei viela demovarauksia</p>
        <p class="state-body">Varaukset ilmestyvat tahan heti, kun joku tekee sellaisen puhelun aikana.</p>
      </div>
    </section>
  </main>
  <script>
    const liveStreamUrl = __API_LIVE_STREAM_URL_JSON__;
    const statusChip = document.getElementById("status-chip");
    const connDot = document.getElementById("conn-dot");
    const connLabel = document.getElementById("conn-label");
    const connDetail = document.getElementById("conn-detail");

    const escapeHtml = (value) =>
      String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");

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

    const CALL_PANEL_IDS = [
      "status-chip",
      "transcript-list",
      "agent-state",
      "capability-list",
    ];
    const LOADING_COPY = "Yhdistetaan live-nakymaan...";
    const IDLE_HEADING = "Ei aktiivista puhelua juuri nyt";
    const IDLE_BODY =
      "Soita numeroon nahdaksesi demon livena. Tama nakyma heraa heti, kun seuraava puhelu alkaa.";

    let currentStatus = null;
    let lastFrameAt = Date.now();

    const TRANSIENT_STATES = new Set(["ringing", "connected"]);
    const TRANSIENT_TIMEOUT_MS = 90000;

    function setPanelText(id, text) {
      document.getElementById(id).textContent = text;
    }

    function setPanelHeadingBody(id, heading, body) {
      const panel = document.getElementById(id);
      panel.textContent = "";
      const headingEl = document.createElement("p");
      headingEl.className = "state-heading";
      headingEl.textContent = heading;
      const bodyEl = document.createElement("p");
      bodyEl.className = "state-body";
      bodyEl.textContent = body;
      panel.appendChild(headingEl);
      panel.appendChild(bodyEl);
    }

    function renderLoading() {
      CALL_PANEL_IDS.forEach((id) => setPanelText(id, LOADING_COPY));
    }

    function renderIdle() {
      currentStatus = null;
      statusChip.className = "";
      CALL_PANEL_IDS.forEach((id) =>
        setPanelHeadingBody(id, IDLE_HEADING, IDLE_BODY)
      );
    }

    function clearNonStatusLoadingCopy() {
      ["transcript-list", "agent-state", "capability-list"].forEach((id) =>
        setPanelText(id, "")
      );
    }

    function renderStatus(state) {
      if (!state) {
        renderIdle();
        return;
      }
      currentStatus = state;
      clearNonStatusLoadingCopy();
      statusChip.textContent = STATUS_LABELS[state] || state;
      statusChip.className = STATUS_CLASS[state] || "";
    }

    renderLoading();

    setInterval(() => {
      if (
        TRANSIENT_STATES.has(currentStatus) &&
        Date.now() - lastFrameAt > TRANSIENT_TIMEOUT_MS
      ) {
        renderIdle();
      }
    }, 5000);

    const source = new EventSource(liveStreamUrl);

    source.onopen = () => {
      connLabel.textContent = "Yhteys muodostettu";
      connDetail.textContent = "";
      connDot.style.background = "var(--success)";
    };

    source.onerror = () => {
      connLabel.textContent = "Yhteys katkesi hetkeksi";
      connDetail.textContent =
        "Selain yrittaa muodostaa yhteyden uudelleen automaattisesti. Sivua ei tarvitse paivittaa kasin.";
      connDot.style.background = "var(--danger)";
    };

    source.onmessage = (event) => {
      lastFrameAt = Date.now();
      const frame = JSON.parse(event.data);
      if (frame.type === "status") {
        renderStatus(frame.state);
      } else if (frame.type === "snapshot") {
        renderStatus(frame.status ? frame.status.state : null);
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
