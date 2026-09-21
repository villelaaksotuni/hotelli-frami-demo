from __future__ import annotations

import asyncio
import html
import json
import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from starlette.responses import StreamingResponse

from app.models.call import utc_now_iso
from app.path_prefix import build_request_app_path
from app.routes.site import HOTEL_PAGE_PATH, TOKENS_CSS_PATH
from app.services.live_broadcast import (
    CAPABILITY_EXAMPLES,
    LIVE_BOARD_LIMIT,
    live_broadcast_hub,
    project_board_fields,
)
from app.services.reservation_provider import reservation_provider

router = APIRouter()
logger = logging.getLogger(__name__)

LIVE_KEEPALIVE_SECONDS = 15


def build_board_entries(limit: int = LIVE_BOARD_LIMIT) -> list[dict[str, Any]]:
    reservations = reservation_provider.list_active_reservations()
    ordered = sorted(reservations, key=lambda record: record.created_at, reverse=True)
    return [project_board_fields(record.to_dict()) for record in ordered[:limit]]


def format_sse_event(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


LIVE_HTML = """<!DOCTYPE html>
<html lang="fi">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Hotelli Frami | Live-näkymä</title>
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

    a { color: inherit; }

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

    h1, h2 {
      margin: 0 0 16px;
      font-weight: 400;
    }

    h1 {
      font-size: clamp(2.5rem, 7vw, 5.5rem);
      letter-spacing: -0.045em;
      line-height: 0.96;
    }

    h2 {
      font-size: clamp(1.35rem, 2.5vw, 2rem);
      letter-spacing: -0.02em;
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

    .panel {
      background: color-mix(in srgb, var(--beigeDark, #f4efe6) 58%, white);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      padding: clamp(1.25rem, 3vw, 2rem);
    }

    .conn-rail {
      display: flex;
      align-items: center;
      gap: 8px;
      padding-bottom: 1.25rem;
      border-bottom: 1px solid var(--line);
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
      min-height: 480px;
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
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
    }

    #transcript-list {
      max-height: 420px;
      overflow-y: auto;
      display: grid;
      gap: 12px;
      padding-right: 4px;
    }

    .transcript-line {
      display: grid;
      gap: 2px;
    }

    .transcript-speaker {
      margin: 0;
      font-size: 13px;
      line-height: 1.4;
      font-weight: 700;
      color: var(--accent);
    }

    .transcript-text {
      margin: 0;
      font-size: 16px;
      line-height: 1.5;
      overflow-wrap: break-word;
    }

    #agent-intent {
      font-size: 16px;
      line-height: 1.5;
      margin: 0 0 4px;
    }

    #agent-step {
      margin: 0 0 16px;
    }

    .agent-slots {
      display: grid;
      gap: 8px;
    }

    .agent-slot-row {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 16px;
    }

    .agent-slot-value {
      font-size: 16px;
      line-height: 1.5;
      text-align: right;
    }

    .agent-slot-value.agent-slot-empty {
      color: var(--ink);
      opacity: 0.45;
    }

    #capability-list {
      display: grid;
      gap: 12px;
    }

    .capability-entry {
      padding: 12px 16px;
      border: 1px solid var(--line);
      border-radius: 16px;
      color: var(--ink);
    }

    .capability-entry.lit {
      border-color: var(--ink);
      background: var(--beigeDark, #f4efe6);
      color: var(--ink);
    }

    .capability-phrase {
      margin: 0;
      font-size: 16px;
      line-height: 1.5;
      overflow-wrap: break-word;
    }

    .board-panel {
      width: 100%;
    }

    #board-list {
      display: grid;
      gap: 12px;
    }

    .board-row {
      padding: 12px 16px;
      border: 1px solid var(--line);
      border-radius: 16px;
      display: grid;
      gap: 4px;
    }

    .board-row-title {
      margin: 0;
      font-size: 16px;
      line-height: 1.5;
      font-weight: 700;
    }

    .board-row-stay,
    .board-row-price {
      margin: 0;
    }

    .board-row-new {
      border-color: #2f6f50;
      animation: board-row-flash 2s ease-out;
    }

    @keyframes board-row-flash {
      from {
        background: rgba(47, 111, 80, 0.16);
      }
      to {
        background: transparent;
      }
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

    @media (prefers-reduced-motion: reduce) {
      *, *::before, *::after {
        scroll-behavior: auto !important;
        animation-duration: 0.01ms !important;
        transition-duration: 0.01ms !important;
      }
    }
  </style>
</head>
<body>
  <a class="skip-link" href="#main-content">Siirry pääsisältöön</a>
  <main class="shell" id="main-content">
    <nav class="top-nav" aria-label="Päänavigaatio">
      <a href="__HOTEL_LINK__">Hotelli Frami</a>
      <a href="__STATS_LINK__">Demon tilastot</a>
    </nav>
    <div class="conn-rail" id="conn-rail" role="status" aria-live="polite">
      <span id="conn-dot" aria-hidden="true"></span>
      <div>
        <span id="conn-label">Yhdistetaan...</span>
        <p id="conn-detail" class="label"></p>
      </div>
    </div>
    <h1>Live-näkymä</h1>
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
              aria-label="Lukitse vieritys viimeisimpaan viestiin"
              aria-pressed="true"
            >Lukitse alimpaan</button>
          </div>
          <div id="transcript-list" role="log" aria-live="polite" aria-relevant="additions text">Yhdistetään live-näkymään...</div>
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
    const CAPABILITY_EXAMPLES = __CAPABILITY_EXAMPLES_JSON__;
    const LIVE_BOARD_LIMIT = __LIVE_BOARD_LIMIT_JSON__;
    const statusChip = document.getElementById("status-chip");
    const connDot = document.getElementById("conn-dot");
    const connLabel = document.getElementById("conn-label");
    const connDetail = document.getElementById("conn-detail");
    const transcriptList = document.getElementById("transcript-list");
    const transcriptScrollLock = document.getElementById("transcript-scroll-lock");
    const agentStatePanel = document.getElementById("agent-state");
    const capabilityListPanel = document.getElementById("capability-list");
    const boardList = document.getElementById("board-list");

    const escapeHtml = (value) =>
      String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");

    const TRANSCRIPT_SPEAKER_LABELS = {
      user: "Soittaja",
      assistant: "Hotelli Framin avustaja",
    };
    const TRANSCRIPT_SCROLL_TOLERANCE_PX = 24;

    let transcriptAutoScroll = true;
    let transcriptReady = false;

    function isTranscriptScrolledToBottom() {
      return (
        transcriptList.scrollHeight -
          transcriptList.scrollTop -
          transcriptList.clientHeight <=
        TRANSCRIPT_SCROLL_TOLERANCE_PX
      );
    }

    function scrollTranscriptToBottom() {
      transcriptList.scrollTop = transcriptList.scrollHeight;
    }

    function clearTranscript() {
      transcriptList.textContent = "";
      transcriptReady = true;
      transcriptAutoScroll = true;
      transcriptScrollLock.setAttribute("aria-pressed", "true");
    }

    function appendTranscriptLine(speaker, text) {
      if (!transcriptReady) {
        clearTranscript();
      }

      const line = document.createElement("div");
      line.className = "transcript-line";

      const speakerEl = document.createElement("p");
      speakerEl.className = "transcript-speaker";
      speakerEl.textContent = TRANSCRIPT_SPEAKER_LABELS[speaker] || speaker;

      const textEl = document.createElement("p");
      textEl.className = "transcript-text";
      textEl.textContent = text;

      line.appendChild(speakerEl);
      line.appendChild(textEl);
      transcriptList.appendChild(line);

      if (transcriptAutoScroll) {
        scrollTranscriptToBottom();
      }
    }

    transcriptList.addEventListener("scroll", () => {
      transcriptAutoScroll = isTranscriptScrolledToBottom();
      transcriptScrollLock.setAttribute(
        "aria-pressed",
        transcriptAutoScroll ? "true" : "false"
      );
    });

    transcriptScrollLock.addEventListener("click", () => {
      transcriptAutoScroll = true;
      transcriptScrollLock.setAttribute("aria-pressed", "true");
      scrollTranscriptToBottom();
    });

    const AGENT_SLOT_ROWS = [
      { key: "arrivalDate", label: "Saapuminen" },
      { key: "nights", label: "Oita" },
      { key: "guests", label: "Vieraita" },
      { key: "area", label: "Alue" },
      { key: "unitName", label: "Huonetyyppi" },
    ];
    const AGENT_SLOT_PLACEHOLDER = "—";

    let agentPanelsReady = false;

    function buildAgentStatePanel() {
      agentStatePanel.textContent = "";

      const intentEl = document.createElement("p");
      intentEl.id = "agent-intent";
      intentEl.textContent = "";
      agentStatePanel.appendChild(intentEl);

      const stepEl = document.createElement("p");
      stepEl.id = "agent-step";
      stepEl.className = "label";
      stepEl.textContent = "";
      agentStatePanel.appendChild(stepEl);

      const slotsEl = document.createElement("div");
      slotsEl.id = "agent-slots";
      slotsEl.className = "agent-slots";

      AGENT_SLOT_ROWS.forEach((row) => {
        const rowEl = document.createElement("div");
        rowEl.className = "agent-slot-row";
        rowEl.dataset.slotKey = row.key;

        const labelEl = document.createElement("span");
        labelEl.className = "agent-slot-label label";
        labelEl.textContent = row.label;

        const valueEl = document.createElement("span");
        valueEl.className = "agent-slot-value agent-slot-empty";
        valueEl.textContent = AGENT_SLOT_PLACEHOLDER;

        rowEl.appendChild(labelEl);
        rowEl.appendChild(valueEl);
        slotsEl.appendChild(rowEl);
      });

      agentStatePanel.appendChild(slotsEl);
    }

    function buildCapabilityListPanel() {
      capabilityListPanel.textContent = "";

      CAPABILITY_EXAMPLES.forEach((entry) => {
        const entryEl = document.createElement("div");
        entryEl.className = "capability-entry";
        entryEl.dataset.tool = entry.tool;

        const phraseEl = document.createElement("p");
        phraseEl.className = "capability-phrase";
        phraseEl.textContent = entry.example_phrase;

        entryEl.appendChild(phraseEl);
        capabilityListPanel.appendChild(entryEl);
      });
    }

    function ensureAgentPanelsReady() {
      if (agentPanelsReady) {
        return;
      }
      buildAgentStatePanel();
      buildCapabilityListPanel();
      agentPanelsReady = true;
    }

    function resetAgentAndCapabilityPanels() {
      agentPanelsReady = false;
      ensureAgentPanelsReady();
    }

    function renderAgentState(agent) {
      ensureAgentPanelsReady();

      const intentEl = document.getElementById("agent-intent");
      const stepEl = document.getElementById("agent-step");
      if (intentEl) {
        intentEl.textContent = (agent && agent.intent) || "";
      }
      if (stepEl) {
        stepEl.textContent = (agent && agent.step) || "";
      }

      const slots = (agent && agent.slots) || {};
      AGENT_SLOT_ROWS.forEach((row) => {
        const rowEl = document.querySelector(
          `.agent-slot-row[data-slot-key="${row.key}"]`
        );
        if (!rowEl) {
          return;
        }
        const valueEl = rowEl.querySelector(".agent-slot-value");
        const value = slots[row.key];
        if (value) {
          valueEl.textContent = value;
          valueEl.classList.remove("agent-slot-empty");
        } else {
          valueEl.textContent = AGENT_SLOT_PLACEHOLDER;
          valueEl.classList.add("agent-slot-empty");
        }
      });
    }

    function renderCapabilityState(firedTools) {
      ensureAgentPanelsReady();

      const fired = new Set(firedTools || []);
      capabilityListPanel.querySelectorAll(".capability-entry").forEach((entryEl) => {
        if (fired.has(entryEl.dataset.tool)) {
          entryEl.classList.add("lit");
        } else {
          entryEl.classList.remove("lit");
        }
      });
    }

    function markCapabilityLit(tool) {
      ensureAgentPanelsReady();

      const entryEl = capabilityListPanel.querySelector(
        `.capability-entry[data-tool="${tool}"]`
      );
      if (entryEl) {
        entryEl.classList.add("lit");
      }
    }

    const BOARD_EMPTY_HEADING = "Ei viela demovarauksia";
    const BOARD_EMPTY_BODY =
      "Varaukset ilmestyvat tahan heti, kun joku tekee sellaisen puhelun aikana.";

    function buildBoardRow(entry) {
      const row = document.createElement("div");
      row.className = "board-row";

      const titleEl = document.createElement("p");
      titleEl.className = "board-row-title";
      titleEl.textContent = `${entry.unit_name} - ${entry.area}`;

      const stayEl = document.createElement("p");
      stayEl.className = "board-row-stay label";
      stayEl.textContent = `${entry.arrival_date} - ${entry.departure_date} (${entry.nights} yota), ${entry.guests} vierasta`;

      const priceEl = document.createElement("p");
      priceEl.className = "board-row-price";
      priceEl.textContent = `${entry.price_total} ${entry.currency}`;

      row.appendChild(titleEl);
      row.appendChild(stayEl);
      row.appendChild(priceEl);
      return row;
    }

    function renderBoardEmpty() {
      boardList.textContent = "";
      const headingEl = document.createElement("p");
      headingEl.className = "state-heading";
      headingEl.textContent = BOARD_EMPTY_HEADING;
      const bodyEl = document.createElement("p");
      bodyEl.className = "state-body";
      bodyEl.textContent = BOARD_EMPTY_BODY;
      boardList.appendChild(headingEl);
      boardList.appendChild(bodyEl);
    }

    function renderBoardSnapshot(entries) {
      boardList.textContent = "";
      if (!entries || entries.length === 0) {
        renderBoardEmpty();
        return;
      }
      entries.forEach((entry) => {
        boardList.appendChild(buildBoardRow(entry));
      });
    }

    function prependBoardReservation(entry) {
      if (!boardList.querySelector(".board-row")) {
        boardList.textContent = "";
      }

      const row = buildBoardRow(entry);
      row.classList.add("board-row-new");
      row.addEventListener(
        "animationend",
        () => {
          row.classList.remove("board-row-new");
        },
        { once: true }
      );
      boardList.insertBefore(row, boardList.firstChild);

      const rows = boardList.querySelectorAll(".board-row");
      for (let i = LIVE_BOARD_LIMIT; i < rows.length; i += 1) {
        rows[i].remove();
      }
    }

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
      transcriptReady = false;
      agentPanelsReady = false;
      CALL_PANEL_IDS.forEach((id) =>
        setPanelHeadingBody(id, IDLE_HEADING, IDLE_BODY)
      );
    }

    function clearNonStatusLoadingCopy() {
      ensureAgentPanelsReady();
    }

    function renderStatus(state) {
      if (!state) {
        renderIdle();
        return;
      }
      if (state === "ringing") {
        clearTranscript();
        resetAgentAndCapabilityPanels();
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
        const snapshotState = frame.status ? frame.status.state : null;
        renderStatus(snapshotState);
        if (snapshotState) {
          renderAgentState(frame.agent);
          renderCapabilityState(frame.capabilities);
        }
        renderBoardSnapshot(frame.board);
      } else if (frame.type === "transcript") {
        appendTranscriptLine(frame.speaker, frame.text);
      } else if (frame.type === "agent") {
        renderAgentState(frame);
      } else if (frame.type === "capability") {
        markCapabilityLit(frame.tool);
      } else if (frame.type === "reservation") {
        prependBoardReservation(frame.reservation);
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
            try:
                board = await asyncio.to_thread(build_board_entries)
            except Exception:
                logger.exception(
                    "Failed to build live reservation board; falling back to empty list"
                )
                board = []

            snapshot = {
                "type": "snapshot",
                "ts": utc_now_iso(),
            }
            snapshot.update(live_broadcast_hub.state_snapshot())
            snapshot["board"] = board
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
        content=_render_live_html(
            build_request_app_path(request, "/api/live/stream"),
            build_request_app_path(request, TOKENS_CSS_PATH),
            build_request_app_path(request, HOTEL_PAGE_PATH),
            build_request_app_path(request, "/tilastot"),
        )
    )


def _render_live_html(
    api_live_stream_url: str,
    tokens_link: str = TOKENS_CSS_PATH,
    hotel_link: str = HOTEL_PAGE_PATH,
    stats_link: str = "/tilastot",
) -> str:
    return (
        LIVE_HTML.replace("__TOKENS_LINK__", html.escape(tokens_link, quote=True))
        .replace("__HOTEL_LINK__", html.escape(hotel_link, quote=True))
        .replace("__STATS_LINK__", html.escape(stats_link, quote=True))
        .replace(
            "__API_LIVE_STREAM_URL_JSON__",
            json.dumps(api_live_stream_url),
        )
        .replace(
            "__CAPABILITY_EXAMPLES_JSON__",
            json.dumps(CAPABILITY_EXAMPLES, ensure_ascii=False),
        )
        .replace(
            "__LIVE_BOARD_LIMIT_JSON__",
            json.dumps(LIVE_BOARD_LIMIT),
        )
    )
