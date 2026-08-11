from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from feedgen.feed import FeedGenerator
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import APP_NAME, SOURCE_LABELS, SOURCE_TAGS, badge_css, palette_entries
from .models import Digest

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=select_autoescape(["html"])
)


def render_page(
    name: str,
    *,
    base_path: str,
    base_url: str,
    page_path: str = "/",
    **context,
) -> str:
    """Render a template to a full HTML string. Works for the live app and static builds.

    `page_path` is the URL path (including base_path) used for the canonical
    og:url, e.g. "/catnews/archive/" or "/archive/hn/2026-08-02/".
    """
    template = _env.get_template(name)
    return template.render(
        app_name=APP_NAME,
        source_labels=SOURCE_LABELS,
        source_tags=SOURCE_TAGS,
        badge_css=badge_css(),
        palette=palette_entries(),
        base_path=base_path,
        base_url=base_url,
        og_url=f"{base_url}{page_path}",
        **context,
    )


def render_markdown(digest: Digest) -> str:
    blocks = [
        f"# {APP_NAME} — {digest.date}",
        "",
    ]
    for i, story in enumerate(digest.stories, 1):
        blocks.append(f"### {i}. {story.title}")
        blocks.append("")
        blocks.append(
            f"- **Source:** {story.source} · **By:** {story.byline or story.author or 'unknown'}"
        )
        if story.why_read:
            blocks.append(f"- **Why read:** {story.why_read}")
        blocks.append(f"- **Link:** {story.url}")
        blocks.append("")
    return "\n".join(blocks)


def _aware(dt) -> datetime:
    """Ensure a datetime carries tzinfo (feedgen requires aware datetimes)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def render_manifest() -> str:
    """Web app manifest (PWA install metadata). Served at {base_path}/manifest.json."""
    manifest = {
        "name": "catnews — The Daily Cat",
        "short_name": APP_NAME,
        "description": "A curated daily digest of HN, arXiv, GitHub, and Register Spill stories.",
        "start_url": "./",
        "scope": "./",
        "display": "standalone",
        "background_color": "#f5f4ed",
        "theme_color": "#1B365D",
        "icons": [
            {"src": "./static/favicon.svg", "sizes": "any", "type": "image/svg+xml"},
            {
                "src": "./static/favicon-180.png",
                "sizes": "180x180",
                "type": "image/png",
            },
        ],
    }
    return json.dumps(manifest, indent=2)


def render_service_worker(urls: list[str], version: str) -> str:
    """Service worker that precaches the whole site for full offline browsing.

    `urls` are relative to the worker's location (e.g. "./", "./index.html",
    "./archive/", "./static/style.css") so the same worker works under any
    base_path. Navigation requests are network-first (fresh daily digest when
    online, cached copy when offline); everything else is cache-first.
    """
    precache = ",\n    ".join(json.dumps(u) for u in urls)
    return f"""// catnews service worker — build {version}
const CACHE = "catnews-{version}";
const PRECACHE = [
    {precache}
];

self.addEventListener("install", (event) => {{
    event.waitUntil(
        caches.open(CACHE).then((cache) => cache.addAll(PRECACHE)).then(() => self.skipWaiting())
    );
}});

self.addEventListener("activate", (event) => {{
    event.waitUntil(
        caches.keys()
            .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
            .then(() => self.clients.claim())
    );
}});

self.addEventListener("fetch", (event) => {{
    const {{
        request
    }} = event;
    if (request.method !== "GET") return;
    const url = new URL(request.url);
    if (url.origin !== location.origin) return;

    if (request.mode === "navigate") {{
        // Fresh digest when online; cached page when offline.
        event.respondWith(
            fetch(request)
                .then((response) => {{
                    const copy = response.clone();
                    caches.open(CACHE).then((cache) => cache.put(request, copy));
                    return response;
                }})
                .catch(() =>
                    caches.match(request).then((match) => match || caches.match("./index.html"))
                )
        );
        return;
    }}

    event.respondWith(
        caches.match(request).then((cached) => {{
            const fresh = fetch(request)
                .then((response) => {{
                    if (response.ok) {{
                        const copy = response.clone();
                        caches.open(CACHE).then((cache) => cache.put(request, copy));
                    }}
                    return response;
                }})
                .catch(() => cached);
            return cached || fresh;
        }})
    );
}});
"""


def walk_site_urls(out_dir: Path) -> list[str]:
    """Relative precache URLs for every file emitted into an output dir.

    Directory navigation URLs (e.g. "./archive/") are added alongside their
    index.html files so offline navigation matches cached entries.
    """
    urls = ["./"]
    for path in sorted(out_dir.rglob("*")):
        if not path.is_file() or path.name == "sw.js":
            continue
        rel = path.relative_to(out_dir).as_posix()
        urls.append("./" + rel)
        if rel.endswith("/index.html"):
            urls.append("./" + rel[: -len("index.html")])
    return list(dict.fromkeys(urls))


def live_site_urls(snapshots: list) -> list[str]:
    """Relative precache URLs for the live FastAPI app (no static build dir)."""
    urls = ["./", "./static/"]
    for path in sorted(STATIC_DIR.rglob("*")):
        if path.is_file():
            urls.append("./static/" + path.relative_to(STATIC_DIR).as_posix())
    urls += ["./archive/", "./stats/", "./sources/", "./api/", "./design/"]
    for snap in snapshots:
        urls.append(f"./archive/{snap.source}/{snap.date.isoformat()}/")
    return list(dict.fromkeys(urls))


def render_rss(digest: Digest, base_url: str) -> str:
    fg = FeedGenerator()
    fg.id(f"{base_url}/")
    fg.title(APP_NAME)
    fg.link(href=base_url, rel="alternate")
    fg.subtitle("catnews — latest across all sources.")
    fg.language("en")

    for story in digest.stories:
        entry = fg.add_entry()
        entry.id(story.url)
        entry.title(story.title)
        entry.link(href=story.url)
        entry.author({"name": story.byline or story.author or "unknown"})
        if story.published:
            entry.published(_aware(story.published))
        parts = []
        if story.why_read:
            parts.append(f"<p><strong>Why read:</strong> {story.why_read}</p>")
        if story.summary:
            parts.append(f"<p>{story.summary}</p>")
        if story.hn_url:
            parts.append(f'<p>Discuss on <a href="{story.hn_url}">Hacker News</a></p>')
        entry.content("".join(parts), type="html")

    return fg.rss_str(pretty=True).decode("utf-8")
