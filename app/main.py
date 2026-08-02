from __future__ import annotations

from datetime import date

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from feedgen.feed import FeedGenerator

from .config import APP_NAME, BASE_URL, DATA_DIR, TAGLINE
from .models import Digest, SiteStats, Story
from .store import load_all, load_digest, load_latest, site_stats

app = FastAPI(title="catnews", description="The Daily Cat — papers and threads worth your time")

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

CAT = r"""  /\_/\
 (=^.^=)
 (")_(")"""


def render(request: Request, name: str, **context) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name=name,
        context={"app_name": APP_NAME, "tagline": TAGLINE, "base_url": BASE_URL, "cat": CAT, **context},
    )


def latest_or_404() -> Digest:
    digest = load_latest(DATA_DIR)
    if digest is None:
        raise HTTPException(status_code=404, detail="No digests published yet. Run `catnews-fetch` first.")
    return digest


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    digest = latest_or_404()
    return render(
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
    return render(request, "archive.html", digests=digests)


@app.get("/stats/", response_class=HTMLResponse)
def stats(request: Request) -> HTMLResponse:
    return render(request, "stats.html", stats=site_stats(DATA_DIR))


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
    digest = latest_or_404()
    blocks = [
        f"# {APP_NAME} — {digest.date}",
        "",
        f"*{TAGLINE}*",
        "",
    ]
    for i, story in enumerate(digest.stories, 1):
        blocks.append(f"### {i}. {story.title}")
        blocks.append("")
        blocks.append(f"- **Source:** {story.source} · **By:** {story.byline or story.author or 'unknown'}")
        if story.signal != "All":
            blocks.append(f"- **Signal:** {story.signal}")
        if story.why_read:
            blocks.append(f"- **Why read:** {story.why_read}")
        blocks.append(f"- **Link:** {story.url}")
        blocks.append("")
    return "\n".join(blocks)


@app.get("/feed.rss")
def rss() -> Response:
    digest = latest_or_404()
    fg = FeedGenerator()
    fg.id(f"{BASE_URL}/")
    fg.title(f"{APP_NAME} — {TAGLINE}")
    fg.link(href=BASE_URL, rel="alternate")
    fg.subtitle(f"The Daily Cat — {digest.date} edition. Papers and threads worth your time.")
    fg.language("en")

    for story in digest.stories:
        entry = fg.add_entry()
        entry.id(story.url)
        entry.title(story.title)
        entry.link(href=story.url)
        entry.author({"name": story.byline or story.author or "unknown"})
        if story.published:
            entry.published(story.published)
        parts = []
        if story.why_read:
            parts.append(f"<p><strong>Why read:</strong> {story.why_read}</p>")
        if story.summary:
            parts.append(f"<p>{story.summary}</p>")
        if story.hn_url:
            parts.append(f'<p>Discuss on <a href="{story.hn_url}">Hacker News</a></p>')
        entry.content("".join(parts), type="html")

    xml = fg.rss_str(pretty=True)
    return Response(content=xml, media_type="application/rss+xml; charset=utf-8")


@app.get("/feed")
def feed_redirect() -> RedirectResponse:
    return RedirectResponse("/feed.rss")
