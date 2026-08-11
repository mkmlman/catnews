"""Validate a generated catnews static site before publishing it."""

from __future__ import annotations

import argparse
import json
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree

REQUIRED_FILES = (
    "index.html",
    "archive/index.html",
    "stats/index.html",
    "sources/index.html",
    "api/index.html",
    "design/index.html",
    "feed.rss",
    "manifest.json",
    "sw.js",
    "api/digest.json",
    "api/sources.json",
    "api/stories.json",
    "api/search.json",
    "api/stats.json",
    "api/trends.json",
    "api/stories.md",
)


class LinkParser(HTMLParser):
    """Collect navigable local references from generated HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.references: list[tuple[Path, str]] = []
        self.current_file = Path()

    def feed_file(self, path: Path) -> None:
        self.current_file = path
        self.feed(path.read_text(encoding="utf-8"))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del tag
        for name, value in attrs:
            if name in {"href", "src"} and value:
                self.references.append((self.current_file, value))


def _local_target(
    reference: str, source: Path, site_dir: Path, base_path: str
) -> Path | None:
    parsed = urlparse(reference)
    if parsed.scheme or parsed.netloc or reference.startswith(("#", "mailto:", "tel:")):
        return None

    path = parsed.path
    if not path:
        return None
    base_path = base_path.rstrip("/")
    if base_path and (path == base_path or path.startswith(base_path + "/")):
        path = path[len(base_path) :]

    if path.startswith("/"):
        target = site_dir / path.lstrip("/")
    else:
        target = source.parent / path
    target = target.resolve()
    try:
        target.relative_to(site_dir.resolve())
    except ValueError:
        raise ValueError(f"reference escapes site: {reference!r} in {source}") from None
    return target


def _exists_as_page(path: Path) -> bool:
    if path.is_file():
        return True
    if path.is_dir():
        return (path / "index.html").is_file()
    if path.suffix == "":
        return (path.with_suffix(".html")).is_file()
    return False


def check_site(site_dir: Path, base_path: str = "") -> list[str]:
    """Return validation errors; an empty list means the artifact is healthy."""
    errors: list[str] = []
    if not site_dir.is_dir():
        return [f"site directory does not exist: {site_dir}"]

    for relative in REQUIRED_FILES:
        if not (site_dir / relative).is_file():
            errors.append(f"missing required file: {relative}")

    for relative in (
        "manifest.json",
        "api/digest.json",
        "api/sources.json",
        "api/stories.json",
        "api/search.json",
        "api/stats.json",
        "api/trends.json",
    ):
        path = site_dir / relative
        if path.is_file():
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                errors.append(f"invalid JSON {relative}: {exc}")

    feed = site_dir / "feed.rss"
    if feed.is_file():
        try:
            ElementTree.fromstring(feed.read_bytes())
        except (OSError, ElementTree.ParseError) as exc:
            errors.append(f"invalid RSS feed: {exc}")

    parser = LinkParser()
    for html_file in sorted(site_dir.rglob("*.html")):
        try:
            parser.feed_file(html_file)
        except OSError as exc:
            errors.append(f"could not read {html_file.relative_to(site_dir)}: {exc}")

    for source, reference in parser.references:
        try:
            target = _local_target(reference, source, site_dir, base_path)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if target is not None and not _exists_as_page(target):
            errors.append(
                f"broken local reference {reference!r} in {source.relative_to(site_dir)}"
            )

    sw = site_dir / "sw.js"
    if sw.is_file() and '"./api/search.json"' not in sw.read_text(encoding="utf-8"):
        errors.append("service worker does not precache api/search.json")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a generated catnews site.")
    parser.add_argument("--site", type=Path, default=Path("site"))
    parser.add_argument(
        "--base-path", default="", help="Pages URL prefix, e.g. /catnews"
    )
    args = parser.parse_args()
    errors = check_site(args.site, args.base_path)
    if errors:
        for error in errors:
            print(f"[catnews] ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
    print(f"[catnews] static site check passed: {args.site}")


if __name__ == "__main__":
    main()
