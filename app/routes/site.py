from __future__ import annotations

import html
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse

from app.config.settings import settings
from app.models.reservation import Unit
from app.path_prefix import build_request_app_path
from app.services.sms_utils import normalize_phone
from app.services.unit_registry import UNITS

router = APIRouter()

HOTEL_PAGE_PATH = "/"
TOKENS_CSS_PATH = "/tokens.css"
TOKENS_CSS_FILE = Path(__file__).resolve().parents[2] / "tokens.css"
HOTEL_IMAGE_ROUTE = "/hotel-images/{image_name}"
HOTEL_IMAGE_DIR = Path(__file__).resolve().parents[1] / "assets" / "hotel"
HOTEL_IMAGE_NAMES = {
    "Framinranta": "framinranta.png",
    "Jokipuisto": "jokipuisto.png",
    "Kampusaukio": "kampusaukio.png",
}
GALLERY_IMAGE_NAMES = {
    "entrance": "gallery-entrance.png",
    "lobby": "gallery-lobby.png",
    "lakeside": "gallery-lakeside.png",
}

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
        '<header class="section-intro">'
        '<span class="section-intro-line" aria-hidden="true"></span>'
        f"<h2>{html.escape(HOW_IT_WORKS_HEADING_FI, quote=True)}</h2>"
        f'<p class="section-lede">{html.escape(HOW_IT_WORKS_INTRO_FI, quote=True)}</p>'
        "</header>"
        "<ol>"
        f"<li>{phone_step_html}</li>"
        f"<li>{live_step_html}</li>"
        f"<li>{html.escape(RESERVE_STEP_FI, quote=True)}</li>"
        "</ol>"
        "</section>"
    )


def _render_room_teaser_row_html(unit: Unit, image_src: str) -> str:
    display_name = html.escape(unit.display_name, quote=True)
    escaped_image_src = html.escape(image_src, quote=True)
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
        '<article class="room-teaser-row">'
        '<div class="room-card-visual">'
        f'<img src="{escaped_image_src}" alt="{display_name}" decoding="sync" />'
        f'<p class="label">{area_text}</p>'
        "</div>"
        '<div class="room-card-copy">'
        f'<p class="room-card-title">{display_name}</p>'
        '<div class="room-card-details">'
        f'<p class="room-card-detail">{rate_text}</p>'
        f'<p class="room-card-detail">{capacity_text}</p>'
        f'<p class="room-card-detail">{nights_text}</p>'
        "</div>"
        "</div>"
        "</article>"
    )


def _first_unit_in_area(area: str) -> Unit:
    for unit in UNITS:
        if unit.area == area:
            return unit
    raise ValueError(f"unit_registry.UNITS has no unit in area {area!r}")


TEASER_UNITS: tuple[Unit, ...] = tuple(_first_unit_in_area(area) for area in ROOM_AREAS_FI)


def _render_hero_gallery_html(request: Request) -> str:
    gallery_items = (
        (
            "entrance",
            "Saapuminen",
            "Hotellin vaalea kivinen sisäänkäynti koivujen ja järven ympäröimänä",
        ),
        (
            "lobby",
            "Yhteiset tilat",
            "Hotellin korkea puuverhoiltu aula, takka ja oleskeluryhmiä",
        ),
        (
            "lakeside",
            "Järviluonto",
            "Tyyni suomalainen järvimaisema ja metsän keskelle rakennettu hotelli",
        ),
    )
    cards_html = "".join(
        (
            f'<figure class="hero-gallery-card hero-gallery-card--{index}">'
            f'<div class="hero-gallery-frame"{(" data-parallax=\"58\"" if index == 3 else "")}>'
            f'<img src="{html.escape(build_request_app_path(request, f"/hotel-images/{GALLERY_IMAGE_NAMES[image_key]}"), quote=True)}" '
            f'alt="{html.escape(alt_text, quote=True)}" loading="eager" '
            'decoding="async" sizes="(max-width: 700px) 90vw, 48vw" />'
            "</div>"
            f'<figcaption class="label">{html.escape(caption, quote=True)}</figcaption>'
            "</figure>"
        )
        for index, (image_key, caption, alt_text) in enumerate(gallery_items, start=1)
    )
    return (
        '<div class="hero-gallery" role="region" aria-label="Hotellin tunnelmia">'
        f"{cards_html}"
        "</div>"
    )


def _render_room_teasers_html(request: Request) -> str:
    rows_html = "".join(
        _render_room_teaser_row_html(
            unit,
            build_request_app_path(
                request, f'/hotel-images/{HOTEL_IMAGE_NAMES[unit.area]}'
            ),
        )
        for unit in TEASER_UNITS
    )
    return (
        '<section class="section-divider" id="room-teasers">'
        '<header class="section-intro">'
        '<span class="section-intro-line" aria-hidden="true"></span>'
        f"<h2>{TEASER_HEADING_FI}</h2>"
        f'<p class="section-lede">{TEASER_INTRO_FI}</p>'
        "</header>"
        f'<div class="room-teaser-list">{rows_html}</div>'
        "</section>"
    )


HOTEL_HTML = r"""<!DOCTYPE html>
<html lang="fi">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Hotelli Frami</title>
  <link rel="stylesheet" href="__TOKENS_LINK__" />
  <style>
    * { box-sizing: border-box; }

    html {
      background: var(--beige);
      color-scheme: light;
    }

    body {
      margin: 0;
      min-height: 100vh;
      background: var(--beige);
      color: var(--primary-900);
      font-family: var(--font-sans);
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
      background: var(--primary-900);
      color: var(--white);
      transform: translateY(-180%);
    }

    .skip-link:focus { transform: translateY(0); }

    h1 {
      width: 100%;
      margin: 0;
      font-size: var(--display-size);
      font-weight: 300;
      letter-spacing: -0.055em;
      line-height: 0.9;
      text-transform: uppercase;
    }

    h1 span { display: block; }

    h1 span:last-child {
      margin-top: -0.06em;
      text-align: right;
    }

    h2 {
      max-width: 18ch;
      margin: 0;
      font-size: var(--section-title-size);
      font-weight: 400;
      letter-spacing: -0.025em;
      line-height: 1.16;
    }

    h2 strong { font-weight: 700; }

    .label {
      margin: 0;
      color: var(--primary-900);
      font-size: 12px;
      font-weight: 500;
      letter-spacing: 0.1em;
      line-height: 1.4;
      text-transform: uppercase;
    }

    .site-header {
      min-height: 82px;
      padding: 0 var(--page-gutter);
      border-bottom: var(--hairline);
      background: var(--beige);
    }

    .top-nav {
      min-height: 82px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 1.5rem;
    }

    .top-nav a {
      display: inline-flex;
      align-items: center;
      gap: 0.6rem;
      color: var(--primary-900);
      font-size: 12px;
      font-weight: 500;
      letter-spacing: 0.1em;
      text-decoration: none;
      text-transform: uppercase;
    }

    .top-nav a::after,
    #how-it-works a::after {
      content: "\2197";
      font-size: 1.15em;
      font-weight: 300;
      transition: transform 180ms ease;
    }

    .top-nav a:hover::after,
    #how-it-works a:hover::after {
      transform: translate(2px, -2px);
    }

    a:focus-visible {
      outline: 1px solid var(--primary-500);
      outline-offset: 5px;
    }

    .shell {
      width: calc(100% - (2 * var(--page-gutter)));
      margin: 0 auto;
      display: grid;
      gap: var(--section-space);
      padding: clamp(2.5rem, 3.5vw, 4rem) 0 var(--section-space);
    }

    .hero {
      position: relative;
      min-height: clamp(44rem, 54vw, 58rem);
      padding-top: clamp(2.5rem, 4vw, 4.5rem);
    }

    .hero h1 {
      position: relative;
      z-index: 2;
      font-size: clamp(4rem, 12.8vw, 12.5rem);
      pointer-events: none;
    }

    .hero h1 span:last-child {
      width: 84%;
      margin-left: 16%;
      text-align: left;
    }

    .hero-gallery {
      position: absolute;
      inset: 0;
      z-index: 1;
    }

    .hero-gallery-card {
      position: absolute;
      margin: 0;
    }

    .hero-gallery-card--1 {
      z-index: 3;
      top: clamp(4rem, 5vw, 4.5rem);
      right: 0;
      width: clamp(10rem, 16vw, 19rem);
    }

    .hero-gallery-card--2 {
      bottom: clamp(3rem, 5vw, 6rem);
      left: 11%;
      width: clamp(8.5rem, 12vw, 14rem);
    }

    .hero-gallery-card--3 {
      left: calc(11% + clamp(8.5rem, 12vw, 14rem) + var(--grid-gap));
      bottom: 0;
      width: min(39vw, 38rem);
    }

    .hero-gallery-frame {
      position: relative;
      overflow: hidden;
      aspect-ratio: 4 / 5;
      border-radius: 2px;
      background: var(--beigeDark);
    }

    .hero-gallery-card--2 .hero-gallery-frame { aspect-ratio: 3 / 4; }

    .hero-gallery-card--3 .hero-gallery-frame { aspect-ratio: 1.85 / 1; }

    .hero-gallery-frame img {
      display: block;
      width: 100%;
      height: 100%;
      object-fit: cover;
    }

    .hero-gallery-frame[data-parallax] {
      --parallax-x: 0px;
      --parallax-y: 0px;
      perspective: 900px;
    }

    .hero-gallery-frame[data-parallax] img {
      position: absolute;
      inset: -20%;
      width: 140%;
      height: 140%;
      transform: translate3d(var(--parallax-x), var(--parallax-y), 0) scale(1.02);
      transform-origin: center;
      will-change: transform;
    }

    .hero-gallery-card figcaption {
      color: var(--gray-700);
    }

    .hero-gallery-card--1 figcaption,
    .hero-gallery-card--2 figcaption {
      position: absolute;
      top: 0;
      right: calc(100% + var(--grid-gap));
      width: 10rem;
      color: var(--primary-900);
      line-height: 1.7;
    }

    .hero-gallery-card--3 figcaption {
      position: absolute;
      top: 0;
      left: calc(100% + var(--grid-gap));
      width: 10rem;
      color: var(--primary-900);
      line-height: 1.7;
    }

    #demo-disclaimer {
      width: min(100%, 54rem);
      margin: calc(var(--section-space) * -0.35) auto 0;
      padding: clamp(1.5rem, 3.2vw, 3rem);
      border: 1px solid var(--golden-500);
      border-radius: 2px;
      background: var(--beigeDark);
      text-align: center;
    }

    #demo-disclaimer p {
      max-width: 47rem;
      margin: 0 auto;
      font-size: clamp(0.875rem, 1.3vw, 1rem);
      font-weight: 400;
    }

    .section-divider {
      padding-top: clamp(3rem, 6vw, 5rem);
      border-top: var(--hairline);
    }

    .section-intro {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 1.5rem;
      margin: 0 auto clamp(3rem, 6vw, 5rem);
      text-align: center;
    }

    .section-intro-line {
      width: 1px;
      height: 30px;
      background: var(--gray-900);
    }

    .section-lede {
      max-width: 48rem;
      margin: 0;
      font-size: clamp(0.875rem, 1.4vw, 1rem);
      font-weight: 300;
    }

    #how-it-works ol {
      margin: 0;
      padding: 0;
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: var(--grid-gap);
      list-style: none;
      counter-reset: steps;
    }

    #how-it-works li {
      min-height: 13rem;
      padding: 1.25rem 0 2rem;
      border-top: var(--hairline);
      color: var(--primary-900);
      font-size: clamp(1.0625rem, 1.4vw, 1.25rem);
      font-weight: 300;
      line-height: 1.65;
      counter-increment: steps;
    }

    #how-it-works li::before {
      content: "0" counter(steps);
      display: block;
      margin-bottom: clamp(2rem, 4vw, 4rem);
      color: var(--primary-900);
      font-size: clamp(1.25rem, 2.2vw, 1.75rem);
      font-weight: 700;
      letter-spacing: 0.06em;
      line-height: 1;
    }

    #how-it-works a {
      display: inline-flex;
      align-items: baseline;
      gap: 0.45rem;
      font-weight: 600;
      text-underline-offset: 0.25em;
    }

    .room-teaser-list {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      align-items: start;
      gap: var(--grid-gap);
    }

    .room-teaser-row {
      min-width: 0;
      display: flex;
      flex-direction: column;
      gap: 0.875rem;
    }

    .room-teaser-row:nth-child(odd) {
      margin-top: clamp(2rem, 4vw, 3.5rem);
    }

    .room-card-visual {
      position: relative;
      aspect-ratio: 3 / 4;
      overflow: hidden;
      border-radius: 2px;
      background: var(--beigeDark);
    }

    .room-card-visual .label {
      position: absolute;
      z-index: 2;
      top: 1rem;
      left: 1rem;
      padding: 0.35rem 0.5rem;
      border-radius: 2px;
      background: var(--white);
    }

    .room-card-visual img {
      display: block;
      width: 100%;
      height: 100%;
      object-fit: cover;
    }

    .room-card-copy {
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
    }

    .room-card-title {
      margin: 0;
      font-size: 18px;
      font-weight: 400;
      line-height: 1.2;
    }

    .room-card-details {
      display: flex;
      flex-wrap: wrap;
      column-gap: 0.75rem;
      row-gap: 0.15rem;
    }

    .room-card-detail {
      margin: 0;
      font-size: 14px;
      font-weight: 300;
    }

    .room-card-detail:not(:last-child)::after {
      content: "\00b7";
      margin-left: 0.75rem;
      color: var(--golden-500);
    }

    @media (prefers-reduced-motion: reduce) {
      *, *::before, *::after {
        scroll-behavior: auto !important;
        transition-duration: 0.01ms !important;
      }

      .hero-gallery-frame[data-parallax] img {
        transform: scale(1.02);
        will-change: auto;
      }
    }

    @media (max-width: 980px) {
      .shell { gap: 4rem; }

      .hero {
        min-height: auto;
        display: grid;
        gap: 3rem;
      }

      .hero-gallery {
        position: static;
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: var(--grid-gap);
      }

      .hero-gallery-card--1,
      .hero-gallery-card--2,
      .hero-gallery-card--3 {
        position: static;
        width: auto;
      }

      .hero-gallery-card figcaption,
      .hero-gallery-card--1 figcaption,
      .hero-gallery-card--2 figcaption,
      .hero-gallery-card--3 figcaption {
        position: static;
        width: auto;
        margin-top: 0.75rem;
        line-height: 1.4;
      }

      .hero-gallery-card--3 {
        grid-column: 1 / -1;
      }

      #how-it-works ol { grid-template-columns: 1fr; }

      #how-it-works li { min-height: 0; }

      #how-it-works li::before { margin-bottom: 1.5rem; }

      .room-teaser-list {
        grid-template-columns: 1fr;
        gap: 3rem;
      }

      .room-teaser-row:nth-child(odd) { margin-top: 0; }
    }

    @media (max-width: 560px) {
      .site-header,
      .top-nav { min-height: 68px; }

      .shell { width: calc(100% - 3rem); }

      h1 { letter-spacing: -0.045em; }

      .hero-gallery {
        gap: 1.5rem 0.75rem;
      }

      #demo-disclaimer { margin-top: -2rem; }
    }
  </style>
</head>
<body>
  <a class="skip-link" href="#main-content">Siirry pääsisältöön</a>
  <header class="site-header">
    <nav class="top-nav" aria-label="Päänavigaatio">
      <a href="__STATS_LINK__">Demon tilastot</a>
      <a href="__LIVE_LINK__">Live-näkymä</a>
    </nav>
  </header>
  <main class="shell" id="main-content">
    <section class="hero" aria-labelledby="hotel-title">
      <h1 id="hotel-title"><span>Hotelli</span><span>Frami</span></h1>
      __HERO_GALLERY_HTML__
    </section>
    <section class="panel" id="demo-disclaimer">
      <p>__DEMO_DISCLAIMER_FI__</p>
    </section>
    __HOW_IT_WORKS_HTML__
    __ROOM_TEASERS_HTML__
  </main>
  <script>
    (() => {
      const motionPreference = window.matchMedia("(prefers-reduced-motion: reduce)");
      const frames = Array.from(document.querySelectorAll("[data-parallax]"));
      let frameRequested = false;

      const updateParallax = () => {
        const viewportHeight = window.innerHeight;
        const mobileScale = window.innerWidth <= 700 ? 0.55 : 1;

        frames.forEach((frame) => {
          const rect = frame.getBoundingClientRect();
          const centerOffset = viewportHeight / 2 - (rect.top + rect.height / 2);
          const progress = centerOffset / (viewportHeight + rect.height);
          const travel = Number(frame.dataset.parallax || 24) * mobileScale;
          const direction = Number(frame.dataset.parallaxDirection || 1);
          const y = Math.max(-travel, Math.min(travel, progress * travel * 2));
          const x = y * 0.12 * direction;

          frame.style.setProperty("--parallax-y", `${y.toFixed(2)}px`);
          frame.style.setProperty("--parallax-x", `${x.toFixed(2)}px`);
        });
        frameRequested = false;
      };

      const requestParallaxUpdate = () => {
        if (motionPreference.matches || frameRequested) return;
        frameRequested = true;
        window.requestAnimationFrame(updateParallax);
      };

      if (!motionPreference.matches && frames.length) {
        requestParallaxUpdate();
        window.addEventListener("scroll", requestParallaxUpdate, { passive: true });
        window.addEventListener("resize", requestParallaxUpdate, { passive: true });
      }
    })();
  </script>
</body>
</html>
"""


def _render_hotel_html(request: Request) -> str:
    live_link = build_request_app_path(request, "/live")
    stats_link = build_request_app_path(request, "/tilastot")
    tokens_link = build_request_app_path(request, TOKENS_CSS_PATH)
    return (
        HOTEL_HTML.replace("__DEMO_DISCLAIMER_FI__", DEMO_DISCLAIMER_FI)
        .replace("__HERO_GALLERY_HTML__", _render_hero_gallery_html(request))
        .replace("__HOW_IT_WORKS_HTML__", _render_how_it_works_html(request))
        .replace("__ROOM_TEASERS_HTML__", _render_room_teasers_html(request))
        .replace("__LIVE_LINK__", html.escape(live_link, quote=True))
        .replace("__STATS_LINK__", html.escape(stats_link, quote=True))
        .replace("__TOKENS_LINK__", html.escape(tokens_link, quote=True))
    )


@router.get(HOTEL_PAGE_PATH)
async def hotel_page(request: Request) -> HTMLResponse:
    return HTMLResponse(content=_render_hotel_html(request))


@router.get(TOKENS_CSS_PATH, include_in_schema=False)
async def design_tokens() -> FileResponse:
    return FileResponse(TOKENS_CSS_FILE, media_type="text/css")


@router.get(HOTEL_IMAGE_ROUTE, include_in_schema=False)
async def hotel_image(image_name: str) -> FileResponse:
    allowed_image_names = set(HOTEL_IMAGE_NAMES.values()) | set(
        GALLERY_IMAGE_NAMES.values()
    )
    if image_name not in allowed_image_names:
        raise HTTPException(status_code=404)
    return FileResponse(HOTEL_IMAGE_DIR / image_name, media_type="image/png")
