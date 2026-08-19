from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path

from feedgen.feed import FeedGenerator
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import (
    APP_NAME,
    REPO_URL,
    SOURCE_LABELS,
    SOURCE_TAGS,
    badge_css,
    palette_entries,
    today_utc,
)
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


def _sw_stable(rel: str) -> bool:
    """True when a built file belongs in the service worker's permanent precache.

    Mutable files (the daily digest, feeds, sitemap, API data) and per-snapshot
    archive pages are excluded: they change on the daily refresh, and
    fingerprinting them would force the service worker to re-download the whole
    cache every single day. Those resources still work offline because the SW
    fetch handler caches them on first visit (network-first for navigations).
    """
    if rel.endswith((".json", ".md")):
        return False
    if rel in ("index.html", "feed.rss", "sitemap.xml"):
        return False
    if rel.startswith("archive/") and rel != "archive/index.html":
        return False
    return not (rel.startswith("api/") and rel != "api/index.html")


def story_anchor(story) -> str:
    """Stable DOM id for a story card — the target of shareable #story-… links.

    Derived from the story URL so the same story shares an anchor across the
    home and snapshot pages.
    """
    return "story-" + hashlib.sha1((story.url or "").encode("utf-8")).hexdigest()[:10]


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
        page_path=page_path,
        og_url=f"{base_url}{page_path}",
        repo_url=REPO_URL,
        asset_version=static_asset_version(),
        story_anchor=story_anchor,
        **context,
    )


def snapshot_nav(
    snapshot: SourceSnapshot, snapshots: list[SourceSnapshot]
) -> tuple[SourceSnapshot | None, SourceSnapshot | None]:
    """Return (older, newer) sibling snapshots for the same source, by date."""
    same = sorted(
        (s for s in snapshots if s.source == snapshot.source),
        key=lambda s: s.date,
    )
    for i, s in enumerate(same):
        if s.date == snapshot.date:
            prev = same[i - 1] if i > 0 else None
            next_snap = same[i + 1] if i < len(same) - 1 else None
            return prev, next_snap
    return None, None


def archive_days(snapshots: list[SourceSnapshot]) -> list[dict]:
    """Group snapshots by calendar day for the archive index, newest first.

    Returns one dict per day::

        {"date": date, "snapshots": [...], "stories": int}
    """
    days: dict[date, list[SourceSnapshot]] = {}
    for snap in snapshots:
        days.setdefault(snap.date, []).append(snap)
    return [
        {
            "date": day,
            "snapshots": sorted(bucket, key=lambda s: s.source),
            "stories": sum(len(s.stories) for s in bucket),
        }
        for day, bucket in sorted(days.items(), key=lambda kv: kv[0], reverse=True)
    ]


def sparkline_points(
    weekly: list[dict], source: str, width: int = 100, height: int = 28
) -> dict | None:
    """Return sparkline geometry for a source's weekly story counts.

    Maps counts onto a `width`x`height` viewBox, oldest week first, with a
    bottom baseline. Returns::

        {"point"|"points": "<x,y> ...", "area": "<x,y> ...", "last": "x,y"}

    where `points` is the trend polyline, `area` is the same polyline closed
    onto the baseline for an area fill, and `last` is the newest point (for an
    end dot). Returns None when the source has fewer than two weeks of data.
    """
    vals = [row["counts"].get(source, 0) for row in weekly if "counts" in row]
    if len(vals) < 2:
        return None
    peak = max(vals) or 1
    pad = 3
    span = height - pad
    n = len(vals)
    points: list[str] = []
    for i, v in enumerate(vals):
        x = pad + i * (width - 2 * pad) / (n - 1)
        y = height - pad - (v / peak) * (span - 2)
        points.append(f"{x:.1f},{y:.1f}")
    baseline = f"{width - pad:.1f},{height - pad:.1f} {pad:.1f},{height - pad:.1f}"
    lx, ly = points[-1].split(",")
    return {
        "points": " ".join(points),
        "area": " ".join([*points, baseline]),
        "last": {"x": lx, "y": ly},
    }


def render_heatmap_svg(daily: list[dict]) -> str:
    """Inline SVG contribution-style heatmap of daily story counts.

    `daily` is the list of dicts from store.daily_counts (oldest first, one
    entry per calendar day). The grid auto-fits the archive span: it starts at
    the Monday of the week containing the first archived day and runs through
    today, so the chart shows the actual active period instead of a fixed
    six-month window. Days with no snapshot render as an empty box (heat-0).
    """
    from datetime import timedelta

    if not daily:
        return ""

    counts = {row["date"]: row["count"] for row in daily}
    max_count = max(counts.values(), default=0) or 1
    total = sum(counts.values())

    today = today_utc()
    first_day = min(counts)
    # Begin on the Monday of the week containing the first archived day so the
    # first column holds that day and no fully-empty leading column leaks in.
    monday = first_day - timedelta(days=first_day.weekday())
    n_weeks = ((today - monday).days // 7) + 1

    cell, gap = 16, 4
    pad_l, pad_r, pad_t, pad_b = 40, 16, 22, 8
    width = pad_l + pad_r + n_weeks * cell + (n_weeks - 1) * gap
    height = pad_t + pad_b + 7 * cell + 6 * gap

    def shade(count: int) -> int:
        if count <= 0:
            return 0
        ratio = count / max_count
        if ratio > 0.75:
            return 4
        if ratio > 0.5:
            return 3
        if ratio > 0.25:
            return 2
        return 1

    parts: list[str] = []
    parts.append(
        f'<svg class="trend-chart heatmap" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="Stories per day, '
        f'{total} total from {monday.isoformat()} to {today.isoformat()}" '
        f'xmlns="http://www.w3.org/2000/svg">'
    )
    # Weekday labels along the left edge (Mon / Wed / Fri).
    for wd, label in ((0, "Mon"), (2, "Wed"), (4, "Fri")):
        y = pad_t + wd * (cell + gap) + cell / 2
        parts.append(
            f'<text x="{pad_l - 6}" y="{y + 3:.1f}" text-anchor="end" '
            f'class="heatmap-day">{label}</text>'
        )
    # Month labels above the first column of each month.
    prev_month = None
    for wi in range(n_weeks):
        col_monday = monday + timedelta(days=wi * 7)
        if col_monday.month != prev_month:
            x = pad_l + wi * (cell + gap) + cell / 2
            parts.append(
                f'<text x="{x:.1f}" y="{pad_t - 6}" text-anchor="middle" '
                f'class="heatmap-month">{col_monday.strftime("%b")}</text>'
            )
            prev_month = col_monday.month
    # Year-boundary hairlines: a subtle dashed separator the day the year
    # ticks over, drawn between two adjacent week columns.
    prev_year = None
    for wi in range(n_weeks):
        col_monday = monday + timedelta(days=wi * 7)
        year = col_monday.year
        if prev_year is not None and year != prev_year:
            x = pad_l + wi * (cell + gap) - gap / 2
            parts.append(
                f'<line class="heatmap-year" x1="{x:.1f}" y1="{pad_t}" '
                f'x2="{x:.1f}" y2="{pad_t + 7 * cell + 6 * gap}"></line>'
            )
        prev_year = year

    for wi in range(n_weeks):
        for wd in range(7):
            day = monday + timedelta(days=wi * 7 + wd)
            count = counts.get(day, 0)
            x = pad_l + wi * (cell + gap)
            y = pad_t + wd * (cell + gap)
            if count == 1:
                label = f"1 story on {day.strftime('%B %d, %Y')}"
            elif count > 1:
                label = f"{count} stories on {day.strftime('%B %d, %Y')}"
            else:
                label = f"No stories on {day.strftime('%B %d, %Y')}"
            parts.append(
                f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" '
                f'class="heat heat-{shade(count)}" data-date="{day.isoformat()}" '
                f'data-count="{count}" tabindex="0" aria-label="{label}"></rect>'
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
    return json.dumps(
        search_index(snapshots), ensure_ascii=False, separators=(",", ":")
    )


def render_json(data: object) -> str:
    """Serialize a generated API artifact compactly and deterministically."""
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str)


def render_fetch_status(status: dict) -> str:
    """Serialize the build-time source freshness report."""
    return render_json(status)


def _aware(dt) -> datetime:
    """Ensure a datetime carries tzinfo (feedgen requires aware datetimes)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def render_manifest() -> str:
    """Web app manifest (PWA install metadata). Served at {base_path}/manifest.json."""
    manifest = {
        "name": "catnews",
        "short_name": APP_NAME,
        "description": "A curated daily digest of HN, arXiv, GitHub, and Register Spill stories.",
        "start_url": "./",
        "scope": "./",
        "display": "standalone",
        "id": "./",
        "background_color": "#f5f4ed",
        "theme_color": "#f5f4ed",
        "icons": [
            {
                "src": "./static/favicon.svg",
                "sizes": "any",
                "type": "image/svg+xml",
                "purpose": "any",
            },
            {
                "src": "./static/favicon-180.png",
                "sizes": "180x180",
                "type": "image/png",
                "purpose": "any",
            },
        ],
    }
    return render_json(manifest)


def render_service_worker(urls: list[str], version: str) -> str:
    """Service worker with app-shell precache and offline browsing.

    `urls` are relative to the worker's location (e.g. "./", "./index.html",
    "./archive/", "./static/style.css") so the same worker works under any
    base_path. Only stable app-shell files belong here (see ``_sw_stable``);
    daily-changing pages and data revalidate via the fetch handler instead.
    Navigation requests and API data are network-first (fresh daily digest and
    search results when online, cached copy when offline); everything else is
    cache-first.
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

    // Fresh responses when online — the daily digest, snapshot pages, and API
    // data all change day to day, so serve the network and refresh the cache;
    // only fall back to the cache when offline. Everything else is cache-first.
    if (request.mode === "navigate" || url.pathname.indexOf("/api/") !== -1) {{
        event.respondWith(
            fetch(request)
                .then((response) => {{
                    const copy = response.clone();
                    caches.open(CACHE).then((cache) => cache.put(request, copy));
                    return response;
                }})
                .catch(() =>
                    caches.match(request).then((match) =>
                        match || (request.mode === "navigate" ? caches.match("./index.html") : null)
                    )
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


def walk_site_urls(out_dir: Path, max_bytes: int = 0) -> list[str]:
    """Relative precache URLs for every file emitted into an output dir.

    Directory navigation URLs (e.g. "./archive/") are added alongside their
    index.html files so offline navigation matches cached entries. Files
    larger than `max_bytes` (0 = unlimited) are skipped so a growing stories
    archive cannot blow the browser's per-cache entry quota.
    """
    urls = ["./"]
    for path in sorted(out_dir.rglob("*")):
        if not path.is_file() or path.name == "sw.js":
            continue
        if max_bytes and path.stat().st_size > max_bytes:
            continue
        rel = path.relative_to(out_dir).as_posix()
        if not _sw_stable(rel):
            continue
        urls.append("./" + rel)
        if rel.endswith("/index.html"):
            urls.append("./" + rel[: -len("index.html")])
    # Search data is precached too (matching live mode) so full-archive search
    # works offline; it is not fingerprinted (see _sw_stable) and revalidates
    # cache-first on each online fetch, so the cache name still stays stable.
    urls += ["./api/search.json", "./api/fetch-status.json"]
    return list(dict.fromkeys(urls))


def render_robots(base_url: str) -> str:
    """Robots.txt: allow all crawlers, point to the sitemap."""
    return f"User-agent: *\nAllow: /\nSitemap: {base_url}/sitemap.xml\n"


def render_sitemap(base_url: str, snapshots: list) -> str:
    """XML sitemap listing every public page (home, sections, snapshots).

    Each URL carries a `<lastmod>` derived from the data it shows: snapshot
    pages use their own date, the shared pages the newest snapshot date.
    """
    newest = max((s.date for s in snapshots), default=date(1970, 1, 1))
    shared = [
        f"{base_url}/",
        f"{base_url}/archive/",
        f"{base_url}/design/",
        f"{base_url}/stats/",
        f"{base_url}/sources/",
        f"{base_url}/api/",
    ]
    entries = [
        f"  <url><loc>{u}</loc><lastmod>{newest}</lastmod></url>" for u in shared
    ]
    entries += [
        f"  <url><loc>{base_url}/archive/{snap.source}/{snap.date.isoformat()}/</loc>"
        f"<lastmod>{snap.date}</lastmod></url>"
        for snap in snapshots
    ]
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(entries)
        + "\n</urlset>\n"
    )


def site_version(out_dir: Path) -> str:
    """Return a content fingerprint for a generated static site.

    Only stable files are fingerprinted (see ``_sw_stable``): mutable digest,
    feed, sitemap, and API data files, and growing per-snapshot archive pages
    are ignored so the fingerprint — and therefore the service worker cache
    name — survives daily data refreshes. The service worker uses it as its
    cache name; a stable name means returning browsers do not re-download the
    entire precache every day.
    """
    digest = hashlib.sha256()
    for path in sorted(out_dir.rglob("*")):
        if not path.is_file() or path.name == "sw.js":
            continue
        rel = path.relative_to(out_dir).as_posix()
        if not _sw_stable(rel):
            continue
        digest.update(rel.encode("utf-8"))
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
        "./api/fetch-status.json",
        "./design/",
    ]
    latest_by_source: dict[str, SourceSnapshot] = {}
    for snap in snapshots:
        latest_by_source[snap.source] = snap
        urls.append(f"./archive/{snap.source}/{snap.date.isoformat()}/")
    urls.extend(f"./api/sources/{source}.json" for source in latest_by_source)
    return list(dict.fromkeys(urls))


def app_version() -> str:
    """Content fingerprint for the live app (templates + static assets).

    Used as the dev service worker's cache name so it stays stable across daily
    data refreshes and only reinstalls when templates or assets actually
    change. The static build uses ``site_version`` instead.
    """
    digest = hashlib.sha256()
    for base in (TEMPLATES_DIR, STATIC_DIR):
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            digest.update(path.relative_to(base).as_posix().encode("utf-8"))
            digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def render_rss(digest: Digest, base_url: str) -> str:
    fg = FeedGenerator()
    fg.id(f"{base_url}/")
    fg.title(APP_NAME)
    fg.link(href=base_url, rel="alternate")
    fg.subtitle("catnews — latest across all sources.")
    fg.language("en")

    # Feed readers expect a single newest-first stream, but the digest
    # interleaves sources round-robin so no source dominates the site. Sort the
    # feed by published date (newest first); undated items sink to the end.
    stories = sorted(
        digest.stories,
        key=lambda s: (
            s.published is not None,
            s.published or datetime.min.replace(tzinfo=UTC),
        ),
        reverse=True,
    )

    for story in stories:
        entry = fg.add_entry(order="append")
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
