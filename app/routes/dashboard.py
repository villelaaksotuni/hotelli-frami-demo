import json

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.path_prefix import build_request_app_path
from app.routes.admin_auth import require_admin_access
from app.services.dashboard_data import dashboard_data_service

router = APIRouter()


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="fi">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Hotelli Frami | Puhelukoonti</title>
  <style>
    :root {
      --bg: #f4efe6;
      --panel: rgba(255, 250, 242, 0.78);
      --panel-strong: rgba(255, 248, 236, 0.94);
      --line: rgba(42, 73, 52, 0.12);
      --ink: #173126;
      --muted: #5a6d61;
      --pine: #244936;
      --forest: #173126;
      --sand: #d8b98e;
      --accent: #b85c38;
      --soft-accent: #f0ddc6;
      --danger: #8a2f2b;
      --success: #2f6f50;
      --shadow: 0 24px 60px rgba(35, 49, 40, 0.12);
      --radius: 24px;
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      min-height: 100vh;
      color: var(--ink);
      font-family: "Trebuchet MS", "Lucida Sans Unicode", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(216, 185, 142, 0.9), transparent 32%),
        radial-gradient(circle at top right, rgba(36, 73, 54, 0.16), transparent 24%),
        linear-gradient(135deg, #efe7d8 0%, #f7f2ea 44%, #e9ece2 100%);
    }

    body::before {
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      background-image:
        linear-gradient(rgba(23, 49, 38, 0.03) 1px, transparent 1px),
        linear-gradient(90deg, rgba(23, 49, 38, 0.03) 1px, transparent 1px);
      background-size: 28px 28px;
      mask-image: linear-gradient(to bottom, rgba(0, 0, 0, 0.45), transparent 90%);
    }

    .shell {
      width: min(1200px, calc(100% - 32px));
      margin: 24px auto 40px;
      display: grid;
      gap: 18px;
    }

    .hero {
      display: grid;
      gap: 18px;
      grid-template-columns: minmax(0, 1.45fr) minmax(320px, 0.9fr);
    }

    .panel {
      background: var(--panel);
      backdrop-filter: blur(14px);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
    }

    .hero-copy {
      padding: 30px;
      position: relative;
      overflow: hidden;
    }

    .hero-copy::after {
      content: "";
      position: absolute;
      width: 280px;
      height: 280px;
      right: -100px;
      bottom: -120px;
      border-radius: 50%;
      background: radial-gradient(circle, rgba(184, 92, 56, 0.28), transparent 62%);
    }

    .eyebrow {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      border-radius: 999px;
      background: rgba(36, 73, 54, 0.08);
      color: var(--pine);
      font-size: 0.82rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }

    h1, h2 {
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      font-weight: 700;
    }

    h1 {
      font-size: clamp(2.5rem, 4vw, 4rem);
      line-height: 0.96;
      margin-top: 18px;
      max-width: 11ch;
    }

    .lede {
      max-width: 56ch;
      margin-top: 18px;
      color: var(--muted);
      font-size: 1rem;
      line-height: 1.65;
    }

    .meta {
      display: grid;
      gap: 12px;
      padding: 24px;
      align-content: start;
    }

    .meta-card {
      padding: 18px 18px 16px;
      border-radius: 20px;
      background: var(--panel-strong);
      border: 1px solid var(--line);
    }

    .meta-label {
      color: var(--muted);
      font-size: 0.82rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }

    .meta-value {
      margin-top: 8px;
      font-size: 1.65rem;
      font-weight: 700;
    }

    .stats {
      display: grid;
      gap: 14px;
      grid-template-columns: repeat(4, minmax(0, 1fr));
    }

    .stat {
      padding: 18px;
      position: relative;
      overflow: hidden;
    }

    .stat::after {
      content: "";
      position: absolute;
      inset: auto -24px -24px auto;
      width: 96px;
      height: 96px;
      border-radius: 50%;
      background: radial-gradient(circle, rgba(216, 185, 142, 0.28), transparent 68%);
    }

    .stat-label {
      color: var(--muted);
      font-size: 0.84rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }

    .stat-value {
      margin-top: 10px;
      font-size: 2rem;
      font-weight: 700;
    }

    .stat-note {
      margin-top: 8px;
      color: var(--muted);
      font-size: 0.92rem;
    }

    .grid {
      display: grid;
      gap: 18px;
      grid-template-columns: minmax(0, 1.1fr) minmax(320px, 0.9fr);
    }

    .section {
      padding: 24px;
    }

    .section-header {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: end;
      margin-bottom: 20px;
    }

    .section-subtitle {
      color: var(--muted);
      font-size: 0.96rem;
      line-height: 1.5;
      max-width: 52ch;
    }

    .trend {
      display: grid;
      grid-template-columns: repeat(7, minmax(0, 1fr));
      gap: 12px;
      min-height: 240px;
      align-items: end;
    }

    .day {
      display: grid;
      gap: 10px;
      justify-items: center;
    }

    .bars {
      width: 100%;
      min-height: 180px;
      display: flex;
      gap: 8px;
      align-items: end;
      justify-content: center;
    }

    .bar {
      width: 18px;
      border-radius: 999px 999px 8px 8px;
      background: linear-gradient(180deg, var(--pine), #4e7b63);
      min-height: 8px;
    }

    .bar.unresolved {
      background: linear-gradient(180deg, var(--accent), #d48f5a);
    }

    .day-total {
      font-size: 0.9rem;
      font-weight: 700;
    }

    .day-label {
      color: var(--muted);
      font-size: 0.85rem;
    }

    .topics {
      display: grid;
      gap: 12px;
    }

    .topic-row {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 12px;
      align-items: center;
    }

    .topic-track {
      width: 100%;
      height: 12px;
      border-radius: 999px;
      background: rgba(36, 73, 54, 0.08);
      overflow: hidden;
    }

    .topic-fill {
      height: 100%;
      border-radius: inherit;
      background: linear-gradient(90deg, #b85c38, #244936);
    }

    .topic-meta {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 8px;
      font-size: 0.95rem;
    }

    .calls {
      display: grid;
      gap: 12px;
    }

    .call {
      padding: 18px;
      border-radius: 20px;
      background: var(--panel-strong);
      border: 1px solid var(--line);
      display: grid;
      gap: 12px;
    }

    .call-top {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: start;
    }

    .call-title {
      font-weight: 700;
      font-size: 1rem;
    }

    .call-subtitle {
      margin-top: 4px;
      color: var(--muted);
      font-size: 0.9rem;
    }

    .call-summary {
      color: var(--ink);
      line-height: 1.55;
    }

    .chips {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }

    .chip {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 8px 12px;
      border-radius: 999px;
      font-size: 0.82rem;
      background: rgba(36, 73, 54, 0.08);
      color: var(--pine);
    }

    .pill {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 8px 12px;
      border-radius: 999px;
      font-size: 0.82rem;
      font-weight: 700;
      letter-spacing: 0.02em;
      min-width: 122px;
    }

    .pill.resolved {
      color: var(--success);
      background: rgba(47, 111, 80, 0.12);
    }

    .pill.unresolved {
      color: var(--danger);
      background: rgba(138, 47, 43, 0.12);
    }

    .empty {
      padding: 36px 24px;
      text-align: center;
      color: var(--muted);
      border: 1px dashed rgba(36, 73, 54, 0.2);
      border-radius: 20px;
      background: rgba(255, 255, 255, 0.45);
    }

    .loading {
      color: var(--muted);
      padding: 24px;
    }

    @media (max-width: 980px) {
      .hero,
      .grid {
        grid-template-columns: 1fr;
      }

      .stats {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
    }

    @media (max-width: 640px) {
      .shell {
        width: min(100% - 18px, 100%);
        margin-top: 10px;
      }

      .hero-copy,
      .meta,
      .section {
        padding: 18px;
      }

      .stats {
        grid-template-columns: 1fr;
      }

      .trend {
        grid-template-columns: repeat(4, minmax(0, 1fr));
      }
    }
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <article class="panel hero-copy">
        <span class="eyebrow">Hotelli Frami • Puheluliikenne</span>
        <h1>Puhelut yhdellä silmäyksellä.</h1>
        <p class="lede">
          Tämä näkymä kokoaa puheluiden määrän, ratkaisuasteen, jatkotoimenpiteet,
          virheet, varauslinkkien jakamisen sekä viimeisimmät yhteydenotot
          yhteen suomenkieliseen koontinäkymään.
        </p>
      </article>
      <aside class="panel meta" id="meta-panel">
        <div class="meta-card">
          <div class="meta-label">Viimeisin päivitys</div>
          <div class="meta-value" id="generated-at">Ladataan…</div>
        </div>
        <div class="meta-card">
          <div class="meta-label">Aikavyöhyke</div>
          <div class="meta-value" id="timezone-label">-</div>
        </div>
        <div class="meta-card">
          <div class="meta-label">Tulkinta</div>
          <div class="meta-value" id="resolution-story">-</div>
        </div>
      </aside>
    </section>

    <section class="stats" id="stats-grid">
      <div class="panel loading">Haetaan tunnuslukuja…</div>
    </section>

    <section class="grid">
      <article class="panel section">
        <div class="section-header">
          <div>
            <h2>7 päivän kehitys</h2>
            <div class="section-subtitle">
              Ratkaistut ja ratkaisemattomat puhelut päivätasolla.
            </div>
          </div>
        </div>
        <div id="trend-section">
          <div class="loading">Ladataan trendiä…</div>
        </div>
      </article>

      <aside class="panel section">
        <div class="section-header">
          <div>
            <h2>Yleisimmät aiheet</h2>
            <div class="section-subtitle">
              Mistä asiakkaat ottivat eniten yhteyttä.
            </div>
          </div>
        </div>
        <div id="topics-section">
          <div class="loading">Ladataan aiheita…</div>
        </div>
      </aside>
    </section>

    <section class="panel section">
      <div class="section-header">
        <div>
          <h2>Viimeisimmät puhelut</h2>
          <div class="section-subtitle">
            Viimeaikaiset yhteydenotot, niiden tila ja lyhyt yhteenveto.
          </div>
        </div>
      </div>
      <div id="calls-section">
        <div class="loading">Ladataan puhelulistaa…</div>
      </div>
    </section>
  </main>

  <script>
    const dashboardDataUrl = __API_DASHBOARD_URL_JSON__;
    const statsGrid = document.getElementById("stats-grid");
    const trendSection = document.getElementById("trend-section");
    const topicsSection = document.getElementById("topics-section");
    const callsSection = document.getElementById("calls-section");
    const generatedAt = document.getElementById("generated-at");
    const timezoneLabel = document.getElementById("timezone-label");
    const resolutionStory = document.getElementById("resolution-story");

    const escapeHtml = (value) =>
      String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");

    const formatSeconds = (value) => {
      if (value === null || value === undefined) {
        return "Ei dataa";
      }
      const rounded = Math.round(value);
      const minutes = Math.floor(rounded / 60);
      const seconds = rounded % 60;
      if (minutes <= 0) {
        return `${seconds} s`;
      }
      return `${minutes} min ${String(seconds).padStart(2, "0")} s`;
    };

    const formatPercent = (value) => {
      if (value === null || value === undefined) {
        return "Ei dataa";
      }
      return `${value.toFixed(1).replace(".", ",")} %`;
    };

    const renderStats = (summary) => {
      const cards = [
        {
          label: "Kaikki puhelut",
          value: summary.total_calls,
          note: "Kaikki tallennetut puhelut",
        },
        {
          label: "Ratkaistut",
          value: summary.resolved_calls,
          note: "Päättyivät ilman jatkotoimia",
        },
        {
          label: "Ratkaisemattomat",
          value: summary.unresolved_calls,
          note: "Vaativat huomiota tai jäivät kesken",
        },
        {
          label: "Ratkaisuaste",
          value: formatPercent(summary.resolution_rate),
          note: "Ratkaistujen osuus kaikista puheluista",
        },
        {
          label: "Jatkotoimet",
          value: summary.follow_up_calls,
          note: "Puhelut, joihin kannattaa palata",
        },
        {
          label: "Virheeseen päättyneet",
          value: summary.error_calls,
          note: "Puhelut, joissa oli virhe tai epäonnistuminen",
        },
        {
          label: "Varaus tehty",
          value: summary.reservation_calls,
          note: "Puhelut, joissa varaus tehtiin",
        },
        {
          label: "Keskimääräinen kesto",
          value: formatSeconds(summary.average_duration_seconds),
          note: `Saapuvat ${summary.inbound_calls} • Lähtevät ${summary.outbound_calls}`,
        },
      ];

      statsGrid.innerHTML = cards.map((card) => `
        <article class="panel stat">
          <div class="stat-label">${escapeHtml(card.label)}</div>
          <div class="stat-value">${escapeHtml(card.value)}</div>
          <div class="stat-note">${escapeHtml(card.note)}</div>
        </article>
      `).join("");
    };

    const renderTrend = (trend) => {
      if (!trend.length) {
        trendSection.innerHTML = '<div class="empty">Viimeisen 7 päivän aikana ei löytynyt puheludataa.</div>';
        return;
      }

      const maxCalls = Math.max(...trend.map((day) => Math.max(day.calls, 1)));
      trendSection.innerHTML = `
        <div class="trend">
          ${trend.map((day) => {
            const resolvedHeight = Math.max(8, Math.round((day.resolved / maxCalls) * 160));
            const unresolvedHeight = Math.max(8, Math.round((day.unresolved / maxCalls) * 160));
            return `
              <div class="day">
                <div class="bars">
                  <div class="bar" style="height:${resolvedHeight}px" title="Ratkaistut ${day.resolved}"></div>
                  <div class="bar unresolved" style="height:${unresolvedHeight}px" title="Ratkaisemattomat ${day.unresolved}"></div>
                </div>
                <div class="day-total">${day.calls} puhelua</div>
                <div class="day-label">${escapeHtml(day.label)}</div>
              </div>
            `;
          }).join("")}
        </div>
      `;
    };

    const renderTopics = (topics) => {
      if (!topics.length) {
        topicsSection.innerHTML = '<div class="empty">Aihejakauma muodostuu, kun puheluista kertyy luokiteltua dataa.</div>';
        return;
      }

      const maxCount = Math.max(...topics.map((topic) => topic.count), 1);
      topicsSection.innerHTML = `
        <div class="topics">
          ${topics.map((topic) => `
            <div class="topic-row">
              <div>
                <div class="topic-meta">
                  <span>${escapeHtml(topic.label)}</span>
                  <strong>${topic.count}</strong>
                </div>
                <div class="topic-track">
                  <div class="topic-fill" style="width:${Math.max(12, (topic.count / maxCount) * 100)}%"></div>
                </div>
              </div>
            </div>
          `).join("")}
        </div>
      `;
    };

    const renderCalls = (calls) => {
      if (!calls.length) {
        callsSection.innerHTML = '<div class="empty">Puheluloki on vielä tyhjä.</div>';
        return;
      }

      callsSection.innerHTML = `
        <div class="calls">
          ${calls.map((call) => `
            <article class="call">
              <div class="call-top">
                <div>
                  <div class="call-title">${escapeHtml(call.direction_label)} • ${escapeHtml(call.counterparty)}</div>
                  <div class="call-subtitle">${escapeHtml(call.occurred_at_local)} • ${escapeHtml(formatSeconds(call.duration_seconds))} • ${escapeHtml(call.status)}</div>
                </div>
                <span class="pill ${escapeHtml(call.resolution_status)}">${escapeHtml(call.resolution_label)}</span>
              </div>
              <div class="chips">
                ${call.topic_labels.map((topic) => `<span class="chip">${escapeHtml(topic)}</span>`).join("")}
                ${call.follow_up_needed ? '<span class="chip">Jatkotoimi</span>' : ""}
                ${call.reservation_created ? '<span class="chip">Varaus tehty</span>' : ""}
                ${call.has_error ? '<span class="chip">Virhe havaittu</span>' : ""}
              </div>
              <div class="call-summary">${escapeHtml(call.summary)}</div>
            </article>
          `).join("")}
        </div>
      `;
    };

    const loadDashboard = async () => {
      try {
        const response = await fetch(dashboardDataUrl, { headers: { "Accept": "application/json" } });
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const payload = await response.json();
        const generatedDate = new Date(payload.generated_at);

        generatedAt.textContent = generatedDate.toLocaleString("fi-FI");
        timezoneLabel.textContent = payload.timezone;
        timezoneLabel.title = payload.timezone;
        resolutionStory.textContent = payload.summary.total_calls
          ? `${payload.summary.resolved_calls} / ${payload.summary.total_calls} puhelua ratkaistiin`
          : "Puheludataa ei ole vielä";

        renderStats(payload.summary);
        renderTrend(payload.trend);
        renderTopics(payload.topic_breakdown);
        renderCalls(payload.recent_calls);
      } catch (error) {
        const message = "Koontidatan lataus epäonnistui.";
        statsGrid.innerHTML = `<div class="panel empty">${message}</div>`;
        trendSection.innerHTML = `<div class="empty">${message}</div>`;
        topicsSection.innerHTML = `<div class="empty">${message}</div>`;
        callsSection.innerHTML = `<div class="empty">${message}</div>`;
        generatedAt.textContent = "Virhe";
        resolutionStory.textContent = "Tarkista palvelimen lokit";
      }
    };

    loadDashboard();
  </script>
</body>
</html>
"""


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard_home(
    request: Request,
    admin_user: Annotated[str, Depends(require_admin_access)],
) -> HTMLResponse:
    del admin_user
    return HTMLResponse(
        content=_render_dashboard_html(
            build_request_app_path(request, "/api/dashboard")
        )
    )


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(
    request: Request,
    admin_user: Annotated[str, Depends(require_admin_access)],
) -> HTMLResponse:
    del admin_user
    return HTMLResponse(
        content=_render_dashboard_html(
            build_request_app_path(request, "/api/dashboard")
        )
    )


@router.get("/api/dashboard")
async def dashboard_data(
    admin_user: Annotated[str, Depends(require_admin_access)],
) -> JSONResponse:
    del admin_user
    return JSONResponse(content=dashboard_data_service.build_dashboard_payload())


def _render_dashboard_html(api_dashboard_url: str) -> str:
    return DASHBOARD_HTML.replace(
        "__API_DASHBOARD_URL_JSON__",
        json.dumps(api_dashboard_url),
    )
