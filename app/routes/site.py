from __future__ import annotations

import html
import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.path_prefix import build_request_app_path
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


def _pluralize_fi(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


def _render_room_card_html(unit) -> str:
    display_name = html.escape(unit.display_name, quote=True)
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
        '<div class="room-card">'
        f'<p class="room-card-title">{display_name}</p>'
        f'<p class="room-card-detail">{rate_text}</p>'
        f'<p class="room-card-detail">{capacity_text}</p>'
        f'<p class="room-card-detail">{nights_text}</p>'
        "</div>"
    )


def _render_unit_cards() -> str:
    sections: list[str] = []
    for area in ROOM_AREAS_FI:
        area_units = [unit for unit in UNITS if unit.area == area]
        if not area_units:
            continue
        cards_html = "".join(_render_room_card_html(unit) for unit in area_units)
        sections.append(
            f"<h3>{html.escape(area, quote=True)}</h3>"
            f'<div class="room-card-grid">{cards_html}</div>'
        )
    return "".join(sections)


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
      --sand: #d8b98e;
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
      line-height: 1.6;
    }

    h1, h2, h3 {
      font-family: Georgia, "Times New Roman", serif;
      font-weight: 700;
      margin: 0 0 16px;
    }

    .hero {
      background: linear-gradient(160deg, var(--sand) 0%, var(--bg) 62%);
      padding: 72px 16px 56px;
      text-align: center;
    }

    .hero-inner {
      max-width: 860px;
      margin: 0 auto;
    }

    .hero-eyebrow {
      margin: 0 0 12px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      font-size: 13px;
      color: var(--accent);
      font-weight: 700;
    }

    .hero h1 {
      font-size: 52px;
      line-height: 1.1;
    }

    .hero-tagline {
      font-size: 19px;
      line-height: 1.5;
      margin: 16px 0 0;
    }

    h2 {
      font-size: 30px;
      line-height: 1.2;
    }

    h3 {
      font-size: 20px;
      line-height: 1.2;
      margin: 24px 0 12px;
    }

    .shell {
      width: min(1100px, calc(100% - 32px));
      margin: 0 auto 56px;
      display: grid;
      gap: 32px;
    }

    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      padding: 32px;
    }

    .disclaimer-panel {
      border: 2px solid var(--accent);
      background: var(--panel-strong);
      font-weight: 700;
    }

    .disclaimer-panel p {
      margin: 0;
    }

    .room-card-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
      gap: 16px;
    }

    .room-card {
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 16px;
      background: var(--panel-strong);
      display: grid;
      gap: 6px;
    }

    .room-card-title {
      margin: 0 0 4px;
      font-weight: 700;
    }

    .room-card-detail {
      margin: 0;
      font-size: 14px;
    }

    ul {
      margin: 0;
      padding-left: 20px;
    }

    li {
      margin-bottom: 8px;
    }

    table {
      width: 100%;
      border-collapse: collapse;
    }

    th, td {
      text-align: left;
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
    }

    .top-nav {
      display: flex;
      gap: 24px;
      justify-content: center;
    }

    .top-nav a {
      color: var(--accent);
      font-weight: 700;
      text-decoration: none;
    }

    @media (max-width: 980px) {
      .hero h1 {
        font-size: 36px;
      }

      .room-card-grid {
        grid-template-columns: 1fr;
      }

      .panel {
        padding: 20px;
      }
    }
  </style>
</head>
<body>
  <header class="hero">
    <div class="hero-inner">
      <p class="hero-eyebrow">Hotelli Frami</p>
      <h1>Koti Framinrannassa, Jokipuistossa ja Kampusaukiolla</h1>
      <p class="hero-tagline">Kolme aluetta, kolmetoista kohdetta ja yksi lämmin vastaanotto.</p>
    </div>
  </header>
  <main class="shell">
    <section class="panel disclaimer-panel" id="demo-disclaimer">
      <p>__DEMO_DISCLAIMER_FI__</p>
    </section>
    <section class="panel" id="majoituskohteemme">
      <h2>Majoituskohteemme</h2>
      __ROOM_CARDS_HTML__
    </section>
    <section class="panel" id="hyva-tietaa">
      <h2>Hyvä tietää</h2>
      <ul>
        <li>Sisäänkirjautuminen alkaa klo 15:00.</li>
        <li>Uloskirjautuminen on viimeistään klo 11:00.</li>
        <li>Avainkoodi toimitetaan tekstiviestillä varauksen puhelinnumeroon tulopäivänä viimeistään klo 15.</li>
        <li>Vastaanotto toimii itsepalveluperiaatteella.</li>
        <li>Hiljaisuus on klo 23:00–08:00.</li>
        <li>Aamiaista ei tarjota. Keittomahdollisuus löytyy omatoimista aamupalan valmistusta varten.</li>
      </ul>
    </section>
    <section class="panel" id="hintaan-sisaltyy">
      <h2>Hintaan sisältyy</h2>
      <ul>
        <li>liinavaatteet ja pyyhkeet</li>
        <li>loppusiivous</li>
        <li>WiFi</li>
        <li>ilmainen pysäköinti</li>
      </ul>
    </section>
    <section class="panel" id="varustelu">
      <h2>Varustelu</h2>
      <ul>
        <li>Kaikissa kohteissa on WiFi, TV ja keittomahdollisuus.</li>
        <li>Osassa kohteita on sauna ja jäähdytys tai ilmastointi.</li>
        <li>Oma kylpyhuone on kaikissa kohteissa paitsi hostelleissa.</li>
        <li>Hostelleissa on yhteiset wc- ja suihkutilat.</li>
      </ul>
    </section>
    <section class="panel" id="kaytannot">
      <h2>Käytännöt</h2>
      <ul>
        <li>Matkasänky lapselle maksaa 24,00 € / yö. Se on varattava etukäteen, ja saatavuus on rajallinen.</li>
        <li>Lemmikit eivät ole sallittuja missään kohteessa.</li>
        <li>Kaikki kohteet ovat savuttomia.</li>
        <li>Vain varauksessa ilmoitettu määrä henkilöitä saa yöpyä.</li>
      </ul>
    </section>
    <section class="panel" id="esteettomyys-ja-sahkoauton-lataus">
      <h2>Esteettömyys ja sähköauton lataus</h2>
      <ul>
        <li>Huoneistohotelli Framinranta on esteetön. Muut kohteet eivät ole esteettömiä.</li>
        <li>Sähköauton lataus on mahdollista vain Huoneistohotelli Framinrannassa. Lataus toimii FramiCharge-sovelluksella.</li>
      </ul>
    </section>
    <section class="panel" id="peruutusehdot">
      <h2>Peruutusehdot</h2>
      <table>
        <thead>
          <tr>
            <th>Tilanne</th>
            <th>Maksuton peruutus viimeistään</th>
            <th>Myöhempi peruutus</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Kesäsesonki</td>
            <td>7 vrk ennen saapumista</td>
            <td>Veloitetaan 100 %</td>
          </tr>
          <tr>
            <td>Sesongin ulkopuolella</td>
            <td>5 vrk ennen saapumista</td>
            <td>Veloitetaan 100 %</td>
          </tr>
          <tr>
            <td>Tapahtuma-ajat</td>
            <td>30 vrk ennen saapumista</td>
            <td>Veloitetaan 100 %</td>
          </tr>
          <tr>
            <td>No-show</td>
            <td>–</td>
            <td>Veloitetaan 100 %</td>
          </tr>
        </tbody>
      </table>
    </section>
    <section class="panel" id="kulkuyhteydet">
      <h2>Kulkuyhteydet</h2>
      <ul>
        <li>Kampusaukion huoneistot, Kampusaukio 7: aivan juna-aseman vieressä. Juna kuljettaa kesällä Framipuistoon ja takaisin.</li>
        <li>Framinrannan keskustan kohteet, Framinkuja 4: juna-asemalle 0,9 km. Muuta julkista liikennettä ei ole.</li>
        <li>Jokipuiston huoneistot: etäisyys Framipuistosta 7 km, autolla noin 8 minuuttia. Julkista liikennettä ei ole.</li>
      </ul>
    </section>
    <footer class="panel">
      <nav class="top-nav">
        <a href="__LIVE_LINK__">Live-näkymä</a>
        <a href="__STATS_LINK__">Demon tilastot</a>
      </nav>
    </footer>
  </main>
</body>
</html>
"""


def _render_hotel_html(request: Request) -> str:
    live_link = build_request_app_path(request, "/live")
    stats_link = build_request_app_path(request, "/tilastot")
    return (
        HOTEL_HTML.replace("__DEMO_DISCLAIMER_FI__", DEMO_DISCLAIMER_FI)
        .replace("__ROOM_CARDS_HTML__", _render_unit_cards())
        .replace("__LIVE_LINK__", html.escape(live_link, quote=True))
        .replace("__STATS_LINK__", html.escape(stats_link, quote=True))
    )


@router.get(HOTEL_PAGE_PATH)
async def hotel_page(request: Request) -> HTMLResponse:
    return HTMLResponse(content=_render_hotel_html(request))
