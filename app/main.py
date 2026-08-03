from __future__ import annotations

from datetime import date

from datetime import date

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from .config import BASE_PATH, BASE_URL, DATA_DIR, SOURCES
from .models import Digest, SourceSnapshot, Story
from .render import render_markdown, render_page, render_rss
from .store import (
    combined_digest,
    load_all_snapshots,
    load_latest_snapshot,
    load_snapshot,
    site_stats,
)

app = FastAPI(title="catnews", description="catnews — curated daily.")

app.mount("/static", StaticFiles(directory="app/static"), name="static")


def page(request: Request, name: str, **context) -> HTMLResponse:
    return HTMLResponse(render_page(name, base_path=BASE_PATH, base_url=BASE_URL, **context))


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    digest = combined_digest(DATA_DIR)
    if digest is None:
        digest = Digest(date=date.today(), stories=[])
    editions = len(load_all_snapshots(DATA_DIR))
    return page(request, "index.html", digest=digest, editions=editions)


@app.get("/archive/", response_class=HTMLResponse)
def archive(request: Request) -> HTMLResponse:
    snapshots = load_all_snapshots(DATA_DIR)
    return page(request, "archive.html", snapshots=snapshots)


@app.get("/archive/{source}/{day}/", response_class=HTMLResponse)
def archive_snapshot(request: Request, source: str, day: date) -> HTMLResponse:
    if source not in SOURCES:
        raise HTTPException(status_code=404, detail=f"Unknown source {source!r}.")
    snap = load_snapshot(source, day, DATA_DIR)
    if snap is None:
        raise HTTPException(status_code=404, detail=f"No snapshot for {source} on {day}.")
    return page(
        request,
        "snapshot.html",
        snapshot=snap,
        label=SOURCES[source]["label"],
    )


@app.get("/stats/", response_class=HTMLResponse)
def stats(request: Request) -> HTMLResponse:
    return page(request, "stats.html", stats=site_stats(DATA_DIR))


# --- JSON API --------------------------------------------------------------


@app.get("/api/sources")
def api_sources() -> list[SourceSnapshot]:
    return load_all_snapshots(DATA_DIR)


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
        raise HTTPException(status_code=404, detail=f"No snapshot for {source} on {day}.")
    return snap


@app.get("/api/digest")
def api_digest() -> SourceSnapshot | dict:
    digest = combined_digest(DATA_DIR)
    if digest is None:
        raise HTTPException(status_code=404, detail="No snapshots published yet. Run `catnews-fetch` first.")
    return digest.model_dump(mode="json")


@app.get("/api/stories")
def api_stories(
    source: str | None = Query(default=None, pattern="^(hn|arxiv|github|registerspill)$"),
) -> list[Story]:
    stories = [s for snap in load_all_snapshots(DATA_DIR) for s in snap.stories]
    if source:
        stories = [s for s in stories if s.source == source]
    return stories


@app.get("/api/stats")
def api_stats() -> dict:
    return site_stats(DATA_DIR).model_dump(mode="json")


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
