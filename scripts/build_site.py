from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import SOURCE_LABELS, SOURCES, source_accent_rgb
from app.models import SourceSnapshot
from app.og_image import render_app_icon, render_maskable_icon, render_og_image
from app.render import (
    archive_days,
    load_dead_links,
    render_dot_chart,
    render_fetch_status,
    render_json,
    render_manifest,
    render_markdown,
    render_page,
    render_robots,
    render_rss,
    render_search_index,
    render_search_shard_index,
    render_service_worker,
    render_sitemap,
    render_source_rss,
    search_index_sharded,
    site_version,
    snapshot_nav,
    sparkline_points,
    walk_site_urls,
)
from app.store import (
    arxiv_category_counts,
    combined_digest,
    daily_counts,
    days_archiving,
    fetch_health,
    fetch_status,
    latest_stories,
    load_all_snapshots,
    site_stats,
    source_registry,
    top_domains,
    weekly_trends,
)

STATIC_DIR = Path(__file__).resolve().parent.parent / "app" / "static"


def clean_output_dir(out_dir: Path, data_dir: Path | None = None) -> None:
    """Remove a prior build only when it cannot overlap project inputs."""
    if out_dir.is_symlink():
        raise SystemExit(f"Build output must not be a symlink: {out_dir}")
    if out_dir.exists() and not out_dir.is_dir():
        raise SystemExit(f"Build output must be a directory: {out_dir}")
    resolved = out_dir.resolve()
    forbidden = {Path("/").resolve(), Path.cwd().resolve(), Path.home().resolve()}
    if resolved in forbidden:
        raise SystemExit(f"Refusing to clean broad build output path: {out_dir}")
    project_root = Path(__file__).resolve().parent.parent
    # Never remove the project itself, an ancestor containing it, or a
    # project subtree other than a direct build-output directory.
    if resolved == project_root or resolved in project_root.parents:
        raise SystemExit(
            f"Refusing to clean project or containing directory: {out_dir}"
        )
    allowed_project_outputs = {
        "site",
        "site_local",
        "preview",
        "catnews",
        "dist",
        "public",
    }
    if project_root in resolved.parents and (
        resolved.parent != project_root or resolved.name not in allowed_project_outputs
    ):
        raise SystemExit(f"Refusing to clean project input directory: {out_dir}")
    protected = [
        (Path(__file__).resolve().parent.parent / "data").resolve(),
        STATIC_DIR.resolve(),
    ]
    if data_dir is not None:
        protected.append(data_dir.resolve())
    for protected_path in protected:
        if resolved == protected_path or resolved in protected_path.parents:
            raise SystemExit(f"Refusing to clean protected input path: {out_dir}")
    if not out_dir.exists():
        return
    if resolved.name not in (
        "site",
        "site_local",
        "preview",
        "catnews",
        "dist",
        "public",
    ):
        print(f"[catnews] warning: cleaning non-standard output dir {out_dir}")
    shutil.rmtree(out_dir)


def write(path: Path, content: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(content)
        tmp.replace(path)
    else:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(path)


def _skip_regex(source: str, start: int) -> int:
    """Return the index just past a regex literal beginning at `start`.

    Called only when the caller has already established that a `/` here
    opens a regex rather than dividing two values.
    """
    i = start + 1
    length = len(source)
    in_class = False
    while i < length:
        ch = source[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "[":
            in_class = True
        elif ch == "]":
            in_class = False
        elif ch == "\n":
            # Unterminated — treat the `/` as a plain operator instead.
            return start + 1
        elif ch == "/" and not in_class:
            i += 1
            while i < length and source[i].isalpha():
                i += 1
            return i
        i += 1
    return start + 1


# Words after which a `/` must be a regex, not a division. Anything else
# ending in an identifier, literal, or closing bracket means division.
_REGEX_PRECEDING_WORDS = frozenset(
    {
        "return",
        "typeof",
        "instanceof",
        "in",
        "of",
        "new",
        "delete",
        "void",
        "do",
        "else",
        "yield",
        "await",
        "case",
        "throw",
    }
)


def _regex_can_start_here(source: str, index: int) -> bool:
    """True if the `/` at `index` may open a regex literal.

    Decided from the previous significant character: after an operator,
    bracket, comma, or statement start a `/` is a regex; after an
    identifier, number, or closing bracket it is division.
    """
    i = index - 1
    while i >= 0 and source[i].isspace():
        i -= 1
    if i < 0:
        return True
    ch = source[i]
    if ch.isalnum() or ch in "_$)]}'\"":
        # Could still be a keyword that permits a regex (`return /x/`).
        end = i + 1
        start = i
        while start >= 0 and (source[start].isalnum() or source[start] in "_$"):
            start -= 1
        return source[start + 1 : end] in _REGEX_PRECEDING_WORDS
    return True


def minify_js(source: str) -> str:
    """Strip JS comments and trailing whitespace without breaking strings.

    A single left-to-right scan that tracks whether it is inside a string,
    template, or regex literal, so a `//` in a URL, a shader string, or a
    character class is never mistaken for a comment. Comments become
    nothing, and a line left empty is dropped — which is also what removes
    the vertical whitespace from the source. Everything else (indentation,
    line breaks inside expressions) is preserved, so this can never change
    what the code does.
    """
    out: list[str] = []
    buf: list[str] = []
    i = 0
    length = len(source)

    def end_line() -> None:
        line = "".join(buf).rstrip()
        buf.clear()
        if line:
            out.append(line)
        elif out:
            out.append("")

    while i < length:
        ch = source[i]

        if ch in "\"'":
            # A quoted string cannot span lines, so track it to its close.
            quote = ch
            buf.append(ch)
            i += 1
            while i < length:
                c = source[i]
                if c == "\\" and i + 1 < length:
                    buf.append(source[i : i + 2])
                    i += 2
                    continue
                buf.append(c)
                i += 1
                if c == quote or c == "\n":
                    if c == "\n":
                        end_line()
                    break
            continue

        if ch == "`":
            # Template literals may span lines and nest ${...}; copy the
            # whole thing verbatim, including any comments inside ${}.
            buf.append(ch)
            i += 1
            while i < length:
                c = source[i]
                if c == "\\" and i + 1 < length:
                    buf.append(source[i : i + 2])
                    i += 2
                    continue
                buf.append(c)
                i += 1
                if c == "`":
                    break
                if c == "\n":
                    line = "".join(buf).rstrip()
                    buf.clear()
                    if line:
                        out.append(line)
                    else:
                        out.append("")
            continue

        if ch == "/" and i + 1 < length:
            nxt = source[i + 1]
            if nxt == "/":
                # Line comment: drop everything up to the newline, which the
                # main loop then handles normally.
                end = source.find("\n", i)
                i = length if end == -1 else end
                continue
            if nxt == "*":
                # Block comment. One that spans newlines terminates the
                # current line, so a banner comment does not weld the
                # following code onto the previous statement.
                end = source.find("*/", i + 2)
                stop = length if end == -1 else end + 2
                if "\n" in source[i:stop]:
                    end_line()
                i = stop
                continue
            if _regex_can_start_here(source, i):
                stop = _skip_regex(source, i)
                buf.append(source[i:stop])
                i = stop
                continue

        if ch == "\n":
            end_line()
            i += 1
            continue

        buf.append(ch)
        i += 1

    end_line()
    while out and not out[-1]:
        out.pop()
    return "\n".join(out) + "\n"


def minify_css(source: str) -> str:
    """Strip CSS comments and collapse blank lines, keeping the cascade.

    Whitespace between selectors and values is preserved because it is
    semantically load-bearing in CSS (`a b`, `margin: 0 auto`, custom
    property fallbacks); only comments and runs of empty lines go.
    """
    without_comments = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    lines = [line.rstrip() for line in without_comments.splitlines()]
    return "\n".join(line for line in lines if line.strip()) + "\n"


MINIFIERS = {"app.js": minify_js, "fluid.js": minify_js, "style.css": minify_css}


def minify_assets(static_dir: Path) -> dict[str, tuple[int, int]]:
    """Minify the shipped CSS/JS in the output dir. Returns before/after sizes.

    Only the build artifact is touched — `app/static/` stays the readable
    source of truth, and `static_asset_version()` keeps hashing the source
    so the cache-busting version still changes when the source changes.
    """
    saved: dict[str, tuple[int, int]] = {}
    for name, minify in MINIFIERS.items():
        path = static_dir / name
        if not path.is_file():
            continue
        original = path.read_text(encoding="utf-8")
        minified = minify(original)
        if len(minified) < len(original):
            path.write_text(minified, encoding="utf-8")
            saved[name] = (len(original), len(minified))
    return saved


def build_site(
    data_dir: Path,
    out_dir: Path,
    base_path: str,
    base_url: str,
    linkcheck: Path | None = None,
    args: argparse.Namespace | None = None,
) -> None:
    snapshots = load_all_snapshots(data_dir)
    if not snapshots:
        raise SystemExit(
            "No snapshots found in data/ — run scripts/fetch_digest.py first."
        )

    clean_output_dir(out_dir, data_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Dead links from the latest weekly link-rot report: a {url -> record}
    # map used to badge rotted story cards. Absent until the first report.
    dead_urls = load_dead_links(linkcheck or (data_dir / "linkcheck.json"))

    digest = combined_digest(data_dir)
    if digest is None:
        raise SystemExit(
            "No stories in snapshots — archive is empty. "
            "Refetch or check data/source_*.json."
        )

    # Per-edition Open Graph cards for every snapshot page (content-addressed
    # by source + date so each day shares a unique card).
    for snap in snapshots:
        og_rel = f"static/og/{snap.source}/{snap.date.isoformat()}.png"
        accent = source_accent_rgb(snap.source)
        write(
            out_dir / og_rel,
            render_og_image(
                date_line=snap.date.strftime("%m.%d.%Y"),
                count_line=f"{len(snap.stories)} STORIES",
                accent=accent,
            ),
        )

    # The home page's own share card is stamped with the edition being shown.
    home_og_rel = f"static/og/home/{digest.date.isoformat()}.png"
    write(
        out_dir / home_og_rel,
        render_og_image(
            date_line=digest.date.strftime("%m.%d.%Y"),
            count_line=f"{len(digest.stories)} STORIES",
            accent=(27, 54, 93),
        ),
    )

    # PWA icons. Chrome will not offer installation without a 192px and a
    # 512px raster marked "any"; the maskable variant covers Android
    # adaptive launchers. All three are generated, so the build needs no
    # image dependency and no committed binaries.
    write(out_dir / "static/icon-192.png", render_app_icon(192))
    write(out_dir / "static/icon-512.png", render_app_icon(512))
    write(out_dir / "static/icon-maskable-512.png", render_maskable_icon())

    # Static assets (style.css, fonts, favicon)
    shutil.copytree(STATIC_DIR, out_dir / "static", dirs_exist_ok=True)
    if args is None or not getattr(args, "no_minify", False):
        saved = minify_assets(out_dir / "static")
        for name, (before, after) in saved.items():
            print(
                f"[catnews] minified static/{name}: {before // 1024}KB -> {after // 1024}KB"
            )

    # Pages
    write(
        out_dir / "index.html",
        render_page(
            "index.html",
            base_path=base_path,
            base_url=base_url,
            page_path="/",
            og_image=f"{base_url}/static/og/home/{digest.date.isoformat()}.png",
            digest=digest,
            freshness=fetch_status(data_dir),
            dead_links=dead_urls,
        ),
    )
    write(
        out_dir / "archive" / "index.html",
        render_page(
            "archive.html",
            base_path=base_path,
            base_url=base_url,
            page_path="/archive/",
            snapshots=snapshots,
            days=archive_days(snapshots),
        ),
    )
    for snap in snapshots:
        prev_snap, next_snap = snapshot_nav(snap, snapshots)
        write(
            out_dir / "archive" / snap.source / snap.date.isoformat() / "index.html",
            render_page(
                "snapshot.html",
                base_path=base_path,
                base_url=base_url,
                page_path=f"/archive/{snap.source}/{snap.date.isoformat()}/",
                og_image=f"{base_url}/static/og/{snap.source}/{snap.date.isoformat()}.png",
                snapshot=snap,
                label=SOURCE_LABELS.get(snap.source, snap.source),
                prev_snapshot=prev_snap,
                next_snapshot=next_snap,
                dead_links=dead_urls,
            ),
        )
    trends = weekly_trends(data_dir, snapshots)
    write(
        out_dir / "stats" / "index.html",
        render_page(
            "stats.html",
            base_path=base_path,
            base_url=base_url,
            page_path="/stats/",
            stats=site_stats(data_dir, snapshots),
            trends=trends,
            dotchart=render_dot_chart(daily_counts(data_dir, snapshots)),
            sparklines={source: sparkline_points(trends, source) for source in SOURCES},
            domains=top_domains(data_dir, snapshots=snapshots),
            arxiv_categories=arxiv_category_counts(data_dir, snapshots),
            days=days_archiving(data_dir, snapshots),
            fetch_health=fetch_health(data_dir, snapshots),
        ),
    )
    write(
        out_dir / "sources" / "index.html",
        render_page(
            "sources.html",
            base_path=base_path,
            base_url=base_url,
            page_path="/sources/",
            sources=source_registry(data_dir),
        ),
    )
    write(
        out_dir / "api" / "index.html",
        render_page(
            "api.html",
            base_path=base_path,
            base_url=base_url,
            page_path="/api/",
            sample_story=digest.stories[0] if digest.stories else None,
            sample_date=digest.date,
        ),
    )
    # Styled GitHub Pages 404 (served for any missing path)
    write(
        out_dir / "404.html",
        render_page(
            "404.html",
            base_path=base_path,
            base_url=base_url,
            page_path="/404/",
        ),
    )
    write(
        out_dir / "design" / "index.html",
        render_page(
            "design.html",
            base_path=base_path,
            base_url=base_url,
            page_path="/design/",
            stats=site_stats(data_dir, snapshots),
        ),
    )

    # Feed + machine-readable files
    if digest:
        write(out_dir / "feed.rss", render_rss(digest, f"{base_url}/"))
        write(out_dir / "api" / "digest.json", digest.model_dump_json())
        write(out_dir / "api" / "stories.md", render_markdown(digest))

    # Per-source feeds: one stream per source with a snapshot, e.g. /feed-hn.rss.
    # snapshots are date-ordered per source (see store.load_all_snapshots:
    # grouped by source, ascending by date), so the last per source is newest.
    # The feed shows the merged latest top-N (see store.latest_stories) rather
    # than just the newest delta-only snapshot, so subscribers keep receiving a
    # full stream even for rolling sources.
    latest_by_source: dict[str, SourceSnapshot] = {}
    for snap in snapshots:
        prev = latest_by_source.get(snap.source)
        if prev is None or snap.date > prev.date:
            latest_by_source[snap.source] = snap
    for source, snapshot in latest_by_source.items():
        merged = SourceSnapshot(
            source=source,
            date=snapshot.date,
            stories=latest_stories(source, data_dir),
        )
        write(
            out_dir / f"feed-{source}.rss",
            render_source_rss(
                source,
                merged,
                f"{base_url}/",
                f"{base_url}/feed-{source}.rss",
            ),
        )

    api = out_dir / "api"
    write(
        api / "sources.json",
        render_json([s.model_dump(mode="json") for s in snapshots]),
    )
    write(
        api / "stories.json",
        render_json(
            [s.model_dump(mode="json") for snap in snapshots for s in snap.stories]
        ),
    )
    write(api / "search.json", render_search_index(snapshots))
    shards = search_index_sharded(snapshots)
    for year, records in shards.items():
        write(api / f"search-{year}.json", render_json(records))
    # Tiny directory so the browser can pick a load strategy without
    # probing for 404s: one combined fetch while it is small, per-year
    # shards once it crosses the documented ~1 MB budget.
    write(api / "search-index.json", render_search_shard_index(shards))
    write(
        api / "dead-links.json",
        render_json(sorted(dead_urls.values(), key=lambda r: r["url"])),
    )
    for source, snapshot in latest_by_source.items():
        write(
            api / "sources" / f"{source}.json",
            snapshot.model_dump_json(),
        )
    write(api / "stats.json", site_stats(data_dir, snapshots).model_dump_json())
    write(
        api / "trends.json",
        render_json(weekly_trends(data_dir, snapshots)),
    )
    write(api / "fetch-status.json", render_fetch_status(fetch_status(data_dir)))

    # SEO: robots.txt + sitemap.xml
    write(out_dir / "robots.txt", render_robots(base_url, base_path))
    write(out_dir / "sitemap.xml", render_sitemap(base_url, snapshots))

    # PWA: manifest + service worker. Precaches only the stable app shell
    # (see render._sw_stable): daily digest, feed, sitemap, and API data files
    # are excluded so a stable fingerprint — and cache name — survives the
    # daily data refresh without re-downloading the whole archive every day.
    # Written last so walk_site_urls sees every emitted file.
    write(out_dir / "manifest.json", render_manifest())
    write(
        out_dir / "sw.js",
        render_service_worker(
            walk_site_urls(out_dir, max_bytes=2_000_000),
            version=site_version(out_dir),
        ),
    )

    print(
        f"[catnews] built {len(snapshots)} snapshots ({len(digest.stories)} stories) -> {out_dir}"
    )
    print(f"[catnews] base_path={base_path!r} base_url={base_url!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the catnews static site.")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Directory holding source_*.json (default: ./data)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("site"),
        help="Output directory (default: ./site)",
    )
    parser.add_argument(
        "--base-path",
        default="/catnews",
        help="URL prefix served under, e.g. /catnews for a GitHub Pages project site",
    )
    parser.add_argument(
        "--base-url",
        default="https://mkmlman.github.io/catnews",
        help="Canonical site URL (used in RSS links)",
    )
    parser.add_argument(
        "--linkcheck",
        type=Path,
        default=None,
        help="Path to a check_links.py JSON report (default: <data-dir>/linkcheck.json)",
    )
    parser.add_argument(
        "--no-minify",
        action="store_true",
        help="Ship style.css/app.js/fluid.js unminified (readable output)",
    )
    args = parser.parse_args()

    data_dir = args.data_dir or (Path(__file__).resolve().parent.parent / "data")
    base_url = args.base_url.rstrip("/")
    base_path = args.base_path.rstrip("/") or ""
    if base_path and not base_path.startswith("/"):
        base_path = "/" + base_path
    if base_path and not base_url.endswith(base_path):
        print(
            f"[catnews] warning: --base-url {base_url!r} does not end with "
            f"--base-path {base_path!r}; canonical URLs may drop the subpath."
        )
    build_site(data_dir, args.out, base_path, base_url, args.linkcheck, args=args)


if __name__ == "__main__":
    main()
