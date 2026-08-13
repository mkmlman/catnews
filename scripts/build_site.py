from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import SOURCES
from app.render import (
    render_fetch_status,
    render_heatmap_svg,
    render_json,
    render_manifest,
    render_markdown,
    render_page,
    render_robots,
    render_rss,
    render_search_index,
    render_service_worker,
    render_sitemap,
    site_version,
    walk_site_urls,
)
from app.store import (
    arxiv_category_counts,
    combined_digest,
    daily_counts,
    days_archiving,
    fetch_health,
    fetch_status,
    load_all_snapshots,
    site_stats,
    source_registry,
    top_domains,
    weekly_trends,
)

STATIC_DIR = Path(__file__).resolve().parent.parent / "app" / "static"


def clean_output_dir(out_dir: Path) -> None:
    """Remove a previous build, guarding against broad or ambiguous targets."""
    if not out_dir.exists():
        return
    if out_dir.is_symlink() or not out_dir.is_dir():
        raise SystemExit(f"Build output must be a real directory: {out_dir}")
    resolved = out_dir.resolve()
    forbidden = {Path("/").resolve(), Path.cwd().resolve(), Path.home().resolve()}
    if resolved in forbidden:
        raise SystemExit(f"Refusing to clean broad build output path: {out_dir}")
    shutil.rmtree(out_dir)


def write(path: Path, content: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "wb" if isinstance(content, bytes) else "w"
    path.open(mode).write(content)


def build_site(
    data_dir: Path,
    out_dir: Path,
    base_path: str,
    base_url: str,
) -> None:
    snapshots = load_all_snapshots(data_dir)
    if not snapshots:
        raise SystemExit(
            "No snapshots found in data/ — run scripts/fetch_digest.py first."
        )

    clean_output_dir(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    digest = combined_digest(data_dir)
    assert digest is not None  # guaranteed: snapshots exist above

    # Static assets (style.css, fonts, favicon)
    shutil.copytree(STATIC_DIR, out_dir / "static", dirs_exist_ok=True)

    # Pages
    write(
        out_dir / "index.html",
        render_page(
            "index.html",
            base_path=base_path,
            base_url=base_url,
            page_path="/",
            digest=digest,
            editions=len(snapshots),
            freshness=fetch_status(data_dir),
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
        ),
    )
    for snap in snapshots:
        write(
            out_dir / "archive" / snap.source / snap.date.isoformat() / "index.html",
            render_page(
                "snapshot.html",
                base_path=base_path,
                base_url=base_url,
                page_path=f"/archive/{snap.source}/{snap.date.isoformat()}/",
                snapshot=snap,
                label=SOURCES[snap.source]["label"],
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
            heatmap=render_heatmap_svg(daily_counts(data_dir, snapshots)),
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
        ),
    )
    write(
        out_dir / "design" / "index.html",
        render_page(
            "design.html",
            base_path=base_path,
            base_url=base_url,
            page_path="/design/",
        ),
    )

    # Feed + machine-readable files
    if digest:
        write(out_dir / "feed.rss", render_rss(digest, f"{base_url}/"))
        write(out_dir / "api" / "digest.json", digest.model_dump_json())
        write(out_dir / "api" / "stories.md", render_markdown(digest))

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
    latest_by_source = {snap.source: snap for snap in snapshots}
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
    write(out_dir / "robots.txt", render_robots(base_url))
    write(out_dir / "sitemap.xml", render_sitemap(base_url, snapshots))

    # PWA: manifest + service worker with full offline precache (written last
    # so walk_site_urls sees every emitted file). stories.json is excluded from
    # precache once it gets large (it grows with the whole archive) while
    # search.json stays cached for offline lookup.
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
    args = parser.parse_args()

    data_dir = args.data_dir or (Path(__file__).resolve().parent.parent / "data")
    build_site(data_dir, args.out, args.base_path, args.base_url)


if __name__ == "__main__":
    main()
