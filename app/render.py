from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from feedgen.feed import FeedGenerator
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import APP_NAME, SOURCE_LABELS, SOURCE_TAGS, badge_css, palette_entries
from .models import Digest, SourceSnapshot

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"


def static_asset_version() -> str:
    """Return a short fingerprint for browser-loaded CSS and JavaScript."""
    digest = hashlib.sha256()
    for name in ("style.css", "app.js"):
        path = STATIC_DIR / name
        digest.update(name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


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
        asset_version=static_asset_version(),
        **context,
    )


def render_trend_svg(trends: list[dict], source_keys: list[str]) -> str:
    """Inline SVG bar chart of stories per week, one bar group per source.

    `trends` is the list of dicts from store.weekly_trends; `source_keys` the
    ordered source keys. Colors come from the badge palette (--badge-{key}-bg
    as fill so light/dark themes both read well).
    """
    if not trends:
        return ""
    width, height = 640, 220
    pad_l, pad_r, pad_t, pad_b = 36, 12, 16, 34
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    n_weeks = len(trends)
    n_sources = len(source_keys)
    max_total = max((c for t in trends for c in t["counts"].values()), default=1) or 1

    group_gap = 24
    group_w = (plot_w - group_gap * (n_weeks - 1)) / n_weeks
    bar_gap = 3
    bar_w = (group_w - bar_gap * (n_sources - 1)) / n_sources

    def y(v: int) -> float:
        return pad_t + plot_h - (plot_h * v / max_total)

    parts: list[str] = []
    parts.append(
        f'<svg class="trend-chart" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="Stories per week by source" xmlns="http://www.w3.org/2000/svg">'
    )
    # horizontal gridlines + y labels
    for i in range(5):
        gy = pad_t + plot_h * i / 4
        val = int(max_total * (1 - i / 4))
        parts.append(
            f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{width - pad_r}" '
            f'y2="{gy:.1f}" class="trend-chart-grid"/>'
        )
        parts.append(
            f'<text x="{pad_l - 6}" y="{gy + 3:.1f}" text-anchor="end" '
            f'class="trend-chart-y">{val}</text>'
        )
    # bars (every source drawn so groups align across weeks)
    for wi, week in enumerate(trends):
        x0 = pad_l + wi * (group_w + group_gap)
        for si, key in enumerate(source_keys):
            val = week["counts"].get(key, 0)
            bx = x0 + si * (bar_w + bar_gap)
            by = y(val)
            parts.append(
                f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bar_w:.1f}" '
                f'height="{pad_t + plot_h - by:.1f}" class="trend-chart-bar" '
                f'fill="var(--badge-{key}-bg)" data-source="{key}"'
                f"{' opacity="0.25"' if not val else ''}/>"
            )
        # week label
        wx = x0 + group_w / 2
        parts.append(
            f'<text x="{wx:.1f}" y="{height - 12}" text-anchor="middle" '
            f'class="trend-chart-x">{week["start"].strftime("%b %d")}</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts)


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


def search_index(snapshots: list[SourceSnapshot]) -> list[dict[str, str]]:
    """Return a compact, deduplicated record set for archive search.

    The full stories API intentionally preserves every historical snapshot. The
    browser search only needs searchable text and one current copy of each
    story, so it gets a much smaller artifact instead.
    """
    records: dict[str, dict[str, str]] = {}
    for snapshot in snapshots:
        for story in snapshot.stories:
            identity = story.external_id or story.url
            key = f"{story.source}:{identity}"
            record = {
                "source": story.source,
                "title": story.title,
                "url": story.url,
            }
            for field in ("author", "byline", "summary", "snippet", "why_read"):
                value = getattr(story, field)
                if value:
                    record[field] = value
            records[key] = record
    return list(records.values())


def render_search_index(snapshots: list[SourceSnapshot]) -> str:
    """Serialize the compact browser-search artifact."""
    return json.dumps(search_index(snapshots), indent=2, ensure_ascii=False)


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


def site_version(out_dir: Path) -> str:
    """Return a content fingerprint for a generated static site.

    The fingerprint changes when any emitted page, asset, or data file changes,
    including multiple rebuilds on the same calendar day. The service worker
    uses it as its cache name so browsers cannot retain an older same-day build.
    """
    digest = hashlib.sha256()
    for path in sorted(out_dir.rglob("*")):
        if not path.is_file() or path.name == "sw.js":
            continue
        digest.update(path.relative_to(out_dir).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def live_site_urls(snapshots: list) -> list[str]:
    """Relative precache URLs for the live FastAPI app (no static build dir)."""
    # StaticFiles serves individual assets, not a directory index at /static/.
    # Including that 404ing URL would make cache.addAll() reject the whole install.
    urls = ["./"]
    for path in sorted(STATIC_DIR.rglob("*")):
        if path.is_file():
            urls.append("./static/" + path.relative_to(STATIC_DIR).as_posix())
    urls += [
        "./archive/",
        "./stats/",
        "./sources/",
        "./api/",
        "./api/search.json",
        "./design/",
    ]
    latest_by_source: dict[str, SourceSnapshot] = {}
    for snap in snapshots:
        latest_by_source[snap.source] = snap
        urls.append(f"./archive/{snap.source}/{snap.date.isoformat()}/")
    urls.extend(f"./api/sources/{source}.json" for source in latest_by_source)
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
