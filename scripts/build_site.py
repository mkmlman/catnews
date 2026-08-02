from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import APP_NAME, TAGLINE  # noqa: E402
from app.models import Digest  # noqa: E402
from app.render import render_markdown, render_page, render_rss  # noqa: E402
from app.store import load_all, site_stats  # noqa: E402

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
    digests = load_all(data_dir)
    if not digests:
        raise SystemExit("No digests found in data/ — run scripts/fetch_digest.py first.")

    latest = digests[-1]

    # Static assets
    write(out_dir / "static" / "style.css", (STATIC_DIR / "style.css").read_bytes())
    shutil.copytree(STATIC_DIR / "fonts", out_dir / "static" / "fonts", dirs_exist_ok=True)

    # Pages
    write(
        out_dir / "index.html",
        render_page(
            "index.html",
            base_path=base_path,
            base_url=base_url,
            digest=latest,
            editions=len(digests),
            stories_json=latest.model_dump_json(),
        ),
    )
    write(
        out_dir / "archive" / "index.html",
        render_page("archive.html", base_path=base_path, base_url=base_url, digests=digests),
    )
    write(
        out_dir / "stats" / "index.html",
        render_page("stats.html", base_path=base_path, base_url=base_url, stats=site_stats(data_dir)),
    )

    # Feed + machine-readable files
    write(out_dir / "feed.rss", render_rss(latest, f"{base_url}/"))

    api = out_dir / "api"
    write(api / "digest.json", latest.model_dump_json(indent=2))
    for digest in digests:
        write(api / f"digest_{digest.date.isoformat()}.json", digest.model_dump_json(indent=2))
    write(
        api / "stories.json",
        json.dumps([s.model_dump(mode="json") for d in digests for s in d.stories], indent=2),
    )
    write(api / "stats.json", site_stats(data_dir).model_dump_json(indent=2))
    write(api / "stories.md", render_markdown(latest))

    print(f"[catnews] built {len(digests)} editions ({sum(len(d.stories) for d in digests)} stories) -> {out_dir}")
    print(f"[catnews] base_path={base_path!r} base_url={base_url!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the catnews static site.")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Directory holding digest_*.json (default: ./data)",
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
