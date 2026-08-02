from __future__ import annotations

from datetime import date

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from .config import APP_NAME, BASE_PATH, BASE_URL, DATA_DIR, TAGLINE
from .models import Digest, SiteStats, Story
from .render import render_markdown, render_page, render_rss
from .store import load_all, load_digest, load_latest, site_stats

app = FastAPI(title="catnews", description="The Daily Cat — papers and threads worth your time")

app.mount("/static", StaticFiles(directory="app/static"), name="static")


def page(request: Request, name: str, **context) -> HTMLResponse:
    return HTMLResponse(render_page(name, base_path=BASE_PATH, base_url=BASE_URL, **context))


def latest_or_404() -> Digest:
    digest = load_latest(DATA_DIR)
    if digest is None:
        raise HTTPException(status_code=404, detail="No digests published yet. Run `catnews-fetch` first.")
    return digest


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    digest = latest_or_404()
    return page(
        request,
        "index.html",
        digest=digest,
        editions=len(load_all(DATA_DIR)),
        stories_json=digest.model_dump_json(),
    )


@app.get("/archive/", response_class=HTMLResponse)
def archive(request: Request) -> HTMLResponse:
    digests = load_all(DATA_DIR)
    if not digests:
        raise HTTPException(status_code=404, detail="No digests published yet.")
    return page(request, "archive.html", digests=digests)


@app.get("/stats/", response_class=HTMLResponse)
def stats(request: Request) -> HTMLResponse:
    return page(request, "stats.html", stats=site_stats(DATA_DIR))


# --- JSON API --------------------------------------------------------------


@app.get("/api/digest")
def api_digest() -> Digest:
    return latest_or_404()


@app.get("/api/digest/{day}")
def api_digest_day(day: date) -> Digest:
    digest = load_digest(day, DATA_DIR)
    if digest is None:
        raise HTTPException(status_code=404, detail=f"No digest for {day}.")
    return digest


@app.get("/api/stories")
def api_stories(
    source: str | None = Query(default=None, pattern="^(hn|arxiv|github)$"),
    signal: str | None = Query(default=None, pattern="^(All|Recommended|Must-Read)$"),
) -> list[Story]:
    stories = [s for d in load_all(DATA_DIR) for s in d.stories]
    if source:
        stories = [s for s in stories if s.source == source]
    if signal:
        stories = [s for s in stories if s.signal == signal]
    return stories


@app.get("/api/stats")
def api_stats() -> SiteStats:
    return site_stats(DATA_DIR)


# --- Markdown / RSS --------------------------------------------------------


@app.get("/api/stories.md", response_class=PlainTextResponse)
def api_stories_markdown() -> str:
    return render_markdown(latest_or_404())


@app.get("/feed.rss")
def rss() -> Response:
    xml = render_rss(latest_or_404(), f"{BASE_URL}/")
    return Response(content=xml, media_type="application/rss+xml; charset=utf-8")


@app.get("/feed")
def feed_redirect() -> RedirectResponse:
    return RedirectResponse("/feed.rss")
