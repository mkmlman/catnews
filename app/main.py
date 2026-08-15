from __future__ import annotations

import re
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

from .config import BASE_PATH, BASE_URL, DATA_DIR, SOURCES, today_utc
from .models import Digest, SourceSnapshot, Story
from .render import (
    live_site_urls,
    render_heatmap_svg,
    render_manifest,
    render_markdown,
    render_page,
    render_rss,
    render_service_worker,
    search_index,
    snapshot_nav,
)
from .store import (
    arxiv_category_counts,
    combined_digest,
    daily_counts,
    days_archiving,
    fetch_health,
    fetch_status,
    load_all_snapshots,
    load_latest_snapshot,
    load_snapshot,
    site_stats,
    source_registry,
    top_domains,
    weekly_trends,
)

app = FastAPI(title="catnews", description="catnews — a curated digest.")

app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).resolve().parent / "static"),
    name="static",
)

SOURCE_PATTERN = "^(?:" + "|".join(re.escape(k) for k in SOURCES) + ")$"


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
    editions = len(load_all_snapshots(DATA_DIR))
    return page(
        request,
        "index.html",
        "/",
        digest=digest,
        editions=editions,
        freshness=fetch_status(DATA_DIR),
    )


@app.get("/archive/", response_class=HTMLResponse)
def archive(request: Request) -> HTMLResponse:
    snapshots = load_all_snapshots(DATA_DIR)
    return page(request, "archive.html", "/archive/", snapshots=snapshots)


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
    snapshots = load_all_snapshots(DATA_DIR)
    prev_snap, next_snap = snapshot_nav(snap, snapshots)
    return page(
        request,
        "snapshot.html",
        f"/archive/{source}/{day.isoformat()}/",
        snapshot=snap,
        label=SOURCES[source]["label"],
        prev_snapshot=prev_snap,
        next_snapshot=next_snap,
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
        domains=top_domains(DATA_DIR),
        arxiv_categories=arxiv_category_counts(DATA_DIR),
        days=days_archiving(DATA_DIR),
        fetch_health=fetch_health(DATA_DIR),
    )


@app.get("/api/", response_class=HTMLResponse)
def api_docs(request: Request) -> HTMLResponse:
    return page(request, "api.html", "/api/")


@app.get("/design/", response_class=HTMLResponse)
def design_system(request: Request) -> HTMLResponse:
    return page(request, "design.html", "/design/")


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
    source: str | None = Query(default=None, pattern=SOURCE_PATTERN),
) -> list[Story]:
    stories = [s for snap in load_all_snapshots(DATA_DIR) for s in snap.stories]
    if source:
        stories = [s for s in stories if s.source == source]
    return stories


@app.get("/api/stories.json")
def api_stories_json(
    source: str | None = Query(default=None, pattern=SOURCE_PATTERN),
) -> list[Story]:
    return api_stories(source)


@app.get("/api/search.json")
def api_search_json() -> list[dict[str, str]]:
    """Compact deduplicated search records for the client-side archive search."""
    return search_index(load_all_snapshots(DATA_DIR))


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
    return RedirectResponse("/feed.rss")


# --- PWA (install + offline) -------------------------------------------------


@app.get("/manifest.json")
def manifest() -> Response:
    return Response(content=render_manifest(), media_type="application/manifest+json")


@app.get("/sw.js")
def service_worker() -> Response:
    urls = live_site_urls(load_all_snapshots(DATA_DIR))
    return Response(
        content=render_service_worker(urls, version=today_utc().isoformat()),
        media_type="application/javascript",
    )
