from __future__ import annotations

import functools
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import (
    HTMLResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles

from .config import (
    BASE_PATH,
    BASE_URL,
    DATA_DIR,
    SOURCES,
    source_accent_rgb,
    today_utc,
)
from .models import Digest, SourceSnapshot, Story
from .og_image import render_og_image
from .render import (
    app_version,
    archive_days,
    live_site_urls,
    load_dead_links,
    render_heatmap_svg,
    render_manifest,
    render_markdown,
    render_page,
    render_robots,
    render_rss,
    render_service_worker,
    render_sitemap,
    render_source_rss,
    search_index,
    sparkline_points,
)
from .store import (
    arxiv_category_counts,
    combined_digest,
    daily_counts,
    days_archiving,
    fetch_health,
    fetch_status,
    latest_stories,
    load_all_snapshots,
    load_latest_snapshot,
    load_snapshot,
    sibling_snapshots,
    site_stats,
    source_registry,
    top_domains,
    weekly_trends,
)

app = FastAPI(title="catnews", description="catnews — a curated digest.")


@functools.lru_cache(maxsize=512)
def _edition_card(source: str, day: str, count: int) -> bytes:
    """Per-snapshot Open Graph card, cached by (source, date, story count).

    `day` is an ISO date string so the cache key is hashable; a source that
    changes its snapshot count re-renders the card.
    """
    accent = source_accent_rgb(source)
    return render_og_image(
        date_line=f"{day[5:7]}.{day[8:10]}.{day[0:4]}",
        count_line=f"{count} STORIES",
        accent=accent,
    )


@functools.lru_cache(maxsize=64)
def _home_card(day: str, count: int) -> bytes:
    """Home page edition card: ink-blue rule, date, total story count."""
    return render_og_image(
        date_line=f"{day[5:7]}.{day[8:10]}.{day[0:4]}",
        count_line=f"{count} STORIES",
        accent=(27, 54, 93),
    )


@app.get("/static/og/home/{day}.png")
def og_home_image(day: date) -> Response:
    """Share card for the combined edition shown on the home page."""
    digest = combined_digest(DATA_DIR)
    if digest is None or digest.date != day:
        raise HTTPException(status_code=404, detail="No such edition.")
    png = _home_card(day.isoformat(), len(digest.stories))
    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400, immutable"},
    )


@app.get("/static/og/{source}/{day}.png")
def og_edition_image(source: str, day: date) -> Response:
    """Per-edition share card for a snapshot page (see scripts/build_site.py).

    Registered before the /static mount so it is matched first; the source
    static dir never contains these generated cards.
    """
    snap = load_snapshot(source, day, DATA_DIR)
    if snap is None:
        raise HTTPException(status_code=404, detail="No such edition.")
    png = _edition_card(source, day.isoformat(), len(snap.stories))
    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400, immutable"},
    )


app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).resolve().parent / "static"),
    name="static",
)


def page(request: Request, name: str, page_path: str = "/", **context) -> HTMLResponse:
    return HTMLResponse(
        render_page(
            name,
            base_path=BASE_PATH,
            base_url=BASE_URL,
            page_path=page_path,
            **context,
        )
    )


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    digest = combined_digest(DATA_DIR)
    if digest is None:
        digest = Digest(date=today_utc(), stories=[])
    return page(
        request,
        "index.html",
        "/",
        og_image=f"{BASE_URL}/static/og/home/{digest.date.isoformat()}.png",
        digest=digest,
        freshness=fetch_status(DATA_DIR),
        dead_links=load_dead_links(DATA_DIR / "linkcheck.json"),
    )


@app.get("/archive/", response_class=HTMLResponse)
def archive(request: Request) -> HTMLResponse:
    snapshots = load_all_snapshots(DATA_DIR)
    return page(
        request,
        "archive.html",
        "/archive/",
        snapshots=snapshots,
        days=archive_days(snapshots),
    )


@app.get("/sources/", response_class=HTMLResponse)
def sources(request: Request) -> HTMLResponse:
    return page(
        request,
        "sources.html",
        "/sources/",
        sources=source_registry(DATA_DIR),
    )


@app.get("/archive/{source}/{day}/", response_class=HTMLResponse)
def archive_snapshot(request: Request, source: str, day: date) -> HTMLResponse:
    if source not in SOURCES:
        raise HTTPException(status_code=404, detail=f"Unknown source {source!r}.")
    snap = load_snapshot(source, day, DATA_DIR)
    if snap is None:
        raise HTTPException(
            status_code=404, detail=f"No snapshot for {source} on {day}."
        )
    prev_snap, next_snap = sibling_snapshots(source, day, DATA_DIR)
    return page(
        request,
        "snapshot.html",
        f"/archive/{source}/{day.isoformat()}/",
        og_image=f"{BASE_URL}/static/og/{source}/{day.isoformat()}.png",
        snapshot=snap,
        label=SOURCES.get(source, {}).get("label", source),
        prev_snapshot=prev_snap,
        next_snapshot=next_snap,
        dead_links=load_dead_links(DATA_DIR / "linkcheck.json"),
    )


@app.get("/stats/", response_class=HTMLResponse)
def stats(request: Request) -> HTMLResponse:
    trends = weekly_trends(DATA_DIR)
    return page(
        request,
        "stats.html",
        "/stats/",
        stats=site_stats(DATA_DIR),
        trends=trends,
        heatmap=render_heatmap_svg(daily_counts(DATA_DIR)),
        sparklines={source: sparkline_points(trends, source) for source in SOURCES},
        domains=top_domains(DATA_DIR),
        arxiv_categories=arxiv_category_counts(DATA_DIR),
        days=days_archiving(DATA_DIR),
        fetch_health=fetch_health(DATA_DIR),
    )


@app.get("/api/", response_class=HTMLResponse)
def api_docs(request: Request) -> HTMLResponse:
    digest = combined_digest(DATA_DIR)
    sample = digest.stories[0] if digest and digest.stories else None
    return page(
        request,
        "api.html",
        "/api/",
        sample_story=sample,
        sample_date=digest.date if digest else None,
    )


@app.get("/design/", response_class=HTMLResponse)
def design_system(request: Request) -> HTMLResponse:
    return page(request, "design.html", "/design/", stats=site_stats(DATA_DIR))


@app.get("/404.html", response_class=HTMLResponse)
def not_found(request: Request) -> HTMLResponse:
    return page(request, "404.html", "/404/")


# --- JSON API --------------------------------------------------------------


@app.get("/api/sources")
def api_sources() -> list[SourceSnapshot]:
    return load_all_snapshots(DATA_DIR)


@app.get("/api/sources/{source}.json")
def api_source_json(source: str) -> SourceSnapshot:
    return api_source(source)


@app.get("/api/sources/{source}")
def api_source(source: str) -> SourceSnapshot:
    snap = load_latest_snapshot(source, DATA_DIR)
    if snap is None:
        raise HTTPException(status_code=404, detail=f"No snapshot for {source}.")
    return snap


@app.get("/api/sources/{source}/{day}.json")
def api_source_day_json(source: str, day: date) -> SourceSnapshot:
    return api_source_day(source, day)


@app.get("/api/sources/{source}/{day}")
def api_source_day(source: str, day: date) -> SourceSnapshot:
    snap = load_snapshot(source, day, DATA_DIR)
    if snap is None:
        raise HTTPException(
            status_code=404, detail=f"No snapshot for {source} on {day}."
        )
    return snap


@app.get("/api/digest")
def api_digest() -> SourceSnapshot | dict:
    digest = combined_digest(DATA_DIR)
    if digest is None:
        raise HTTPException(
            status_code=404,
            detail="No snapshots published yet. Run `catnews-fetch` first.",
        )
    return digest.model_dump(mode="json")


@app.get("/api/digest.json")
def api_digest_json() -> SourceSnapshot | dict:
    return api_digest()


@app.get("/api/stories")
def api_stories(
    source: str | None = Query(default=None),
) -> list[Story]:
    if source is not None and source not in SOURCES:
        raise HTTPException(status_code=404, detail=f"Unknown source {source!r}.")
    stories = [s for snap in load_all_snapshots(DATA_DIR) for s in snap.stories]
    if source:
        stories = [s for s in stories if s.source == source]
    return stories


@app.get("/api/stories.json")
def api_stories_json(
    source: str | None = Query(default=None),
) -> list[Story]:
    return api_stories(source)


@app.get("/api/search.json")
def api_search_json() -> list[dict[str, str]]:
    """Compact deduplicated search records for the client-side archive search."""
    return search_index(load_all_snapshots(DATA_DIR))


@app.get("/api/search")
def api_search() -> list[dict[str, str]]:
    return api_search_json()


@app.get("/api/dead-links")
@app.get("/api/dead-links.json")
def api_dead_links() -> list[dict]:
    """Story URLs the weekly link-rot check found dead, for API consumers."""
    return sorted(
        load_dead_links(DATA_DIR / "linkcheck.json").values(),
        key=lambda r: r["url"],
    )


@app.get("/api/stats")
def api_stats() -> dict:
    return site_stats(DATA_DIR).model_dump(mode="json")


@app.get("/api/stats.json")
def api_stats_json() -> dict:
    return api_stats()


@app.get("/api/trends")
def api_trends() -> list[dict]:
    return weekly_trends(DATA_DIR)


@app.get("/api/trends.json")
def api_trends_json() -> list[dict]:
    return api_trends()


@app.get("/api/fetch-status.json")
def api_fetch_status_json() -> dict:
    return fetch_status(DATA_DIR)


@app.get("/api/fetch-status")
def api_fetch_status() -> dict:
    return api_fetch_status_json()


@app.get("/api/sources.json")
def api_sources_json() -> list[SourceSnapshot]:
    return api_sources()


# --- Markdown / RSS --------------------------------------------------------


@app.get("/api/stories.md", response_class=PlainTextResponse)
def api_stories_markdown() -> str:
    digest = combined_digest(DATA_DIR)
    if digest is None:
        raise HTTPException(status_code=404, detail="No snapshots published yet.")
    return render_markdown(digest)


@app.get("/feed.rss")
def rss() -> Response:
    digest = combined_digest(DATA_DIR)
    if digest is None:
        raise HTTPException(status_code=404, detail="No snapshots published yet.")
    xml = render_rss(digest, f"{BASE_URL}/")
    return Response(content=xml, media_type="application/rss+xml; charset=utf-8")


@app.get("/feed")
def feed_redirect() -> RedirectResponse:
    return RedirectResponse(BASE_PATH + "/feed.rss")


@app.get("/feed-{source}.rss")
def source_rss(source: str) -> Response:
    """Per-source RSS feed (e.g. /feed-hn.rss), mirroring the static build."""
    if source not in SOURCES:
        raise HTTPException(status_code=404, detail=f"Unknown source {source!r}.")
    snap = load_latest_snapshot(source, DATA_DIR)
    if snap is None:
        raise HTTPException(status_code=404, detail=f"No snapshot for {source}.")
    stories = latest_stories(source, DATA_DIR)
    if not stories:
        raise HTTPException(status_code=404, detail=f"No snapshot for {source}.")
    merged = SourceSnapshot(source=source, date=snap.date, stories=stories)
    xml = render_source_rss(
        source, merged, f"{BASE_URL}/", f"{BASE_URL}/feed-{source}.rss"
    )
    return Response(content=xml, media_type="application/rss+xml; charset=utf-8")


# --- PWA (install + offline) -------------------------------------------------


@app.get("/sitemap.xml")
def sitemap() -> Response:
    xml = render_sitemap(BASE_URL, load_all_snapshots(DATA_DIR))
    return Response(content=xml, media_type="application/xml; charset=utf-8")


@app.get("/robots.txt")
def robots() -> PlainTextResponse:
    return PlainTextResponse(render_robots(BASE_URL))


@app.get("/manifest.json")
def manifest() -> Response:
    return Response(content=render_manifest(), media_type="application/manifest+json")


@app.get("/sw.js")
def service_worker() -> Response:
    urls = live_site_urls(load_all_snapshots(DATA_DIR))
    return Response(
        content=render_service_worker(urls, version=app_version()),
        media_type="application/javascript",
    )
