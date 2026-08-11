from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import SOURCES, today_utc
from app.render import (
    render_manifest,
    render_markdown,
    render_page,
    render_rss,
    render_service_worker,
    walk_site_urls,
)
from app.store import (
    combined_digest,
    load_all_snapshots,
    site_stats,
    source_registry,
)

STATIC_DIR = Path(__file__).resolve().parent.parent / "app" / "static"


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
    write(
        out_dir / "stats" / "index.html",
        render_page(
            "stats.html",
            base_path=base_path,
            base_url=base_url,
            page_path="/stats/",
            stats=site_stats(data_dir),
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
        write(out_dir / "api" / "digest.json", digest.model_dump_json(indent=2))
        write(out_dir / "api" / "stories.md", render_markdown(digest))

    api = out_dir / "api"
    write(
        api / "sources.json",
        json.dumps([s.model_dump(mode="json") for s in snapshots], indent=2),
    )
    write(
        api / "stories.json",
        json.dumps(
            [s.model_dump(mode="json") for snap in snapshots for s in snap.stories],
            indent=2,
        ),
    )
    write(api / "stats.json", site_stats(data_dir).model_dump_json(indent=2))

    # PWA: manifest + service worker with full offline precache (written last
    # so walk_site_urls sees every emitted file)
    version = today_utc().isoformat()
    write(out_dir / "manifest.json", render_manifest())
    write(
        out_dir / "sw.js",
        render_service_worker(walk_site_urls(out_dir), version=version),
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
