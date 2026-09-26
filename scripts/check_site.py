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
    "robots.txt",
    "sitemap.xml",
    "api/digest.json",
    "api/sources.json",
    "api/stories.json",
    "api/search.json",
    "api/stats.json",
    "api/trends.json",
    "api/fetch-status.json",
    "api/dead-links.json",
    "api/stories.md",
)


class LinkParser(HTMLParser):
    """Collect navigable local references from generated HTML.

    Beyond href/src, also collects og:image / twitter:image meta content,
    so a broken social card fails validation instead of shipping silently.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.references: list[tuple[Path, str]] = []
        self.current_file = Path()

    def feed_file(self, path: Path) -> None:
        self.current_file = path
        self.reset()
        self.feed(path.read_text(encoding="utf-8"))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = dict(attrs)
        for name, value in attrs:
            if name in {"href", "src"} and value:
                self.references.append((self.current_file, value))
        if tag == "meta":
            prop = (attr_dict.get("property") or attr_dict.get("name") or "").lower()
            if prop in {"og:image", "twitter:image"}:
                content = attr_dict.get("content")
                if content:
                    self.references.append((self.current_file, content))


def _local_target(
    reference: str, source: Path, site_dir: Path, base_path: str, base_url: str = ""
) -> Path | None:
    parsed = urlparse(reference)
    # Absolute URLs on the same site (canonical, og:image) still map to files.
    if parsed.scheme or parsed.netloc:
        if not base_url:
            return None
        base_parsed = urlparse(base_url.rstrip("/"))
        if (parsed.scheme, parsed.netloc) != (base_parsed.scheme, base_parsed.netloc):
            return None
        # Fall through with path below after same-origin check.
    elif reference.startswith(("#", "mailto:", "tel:")):
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


def _check_rss(path: Path, errors: list[str]) -> None:
    """Well-formedness plus feed-reader essentials: self link, date, GUIDs."""
    root = ElementTree.fromstring(path.read_bytes())
    NS = {"atom": "http://www.w3.org/2005/Atom"}
    if root.find("channel/atom:link[@rel='self']", NS) is None:
        errors.append(f"RSS {path.name} missing atom self link")
    channel = root.find("channel")
    if channel is not None:
        has_date = (
            channel.find("lastBuildDate") is not None
            or channel.find("updated") is not None
            or channel.find("pubDate") is not None
        )
        if not has_date:
            errors.append(f"RSS {path.name} missing channel date")
        guids: list[str] = []
        for item in channel.findall("item"):
            title = item.find("title")
            guid = item.find("guid")
            if title is None or not (title.text or "").strip():
                errors.append(f"RSS {path.name} has item without title")
            if guid is None or not (guid.text or "").strip():
                errors.append(f"RSS {path.name} has item without guid")
            elif guid.text:
                guids.append(guid.text.strip())
        if len(set(guids)) != len(guids):
            errors.append(f"RSS {path.name} has duplicate guids")


def check_site(site_dir: Path, base_path: str = "", base_url: str = "") -> list[str]:
    """Return validation errors; an empty list means the artifact is healthy."""
    errors: list[str] = []
    if not site_dir.is_dir():
        return [f"site directory does not exist: {site_dir}"]
    if not base_url:
        # Derive same-origin base for absolute URL checks from sitemap/canonical.
        try:
            from xml.etree import ElementTree as _ET

            _sm = _ET.parse(site_dir / "sitemap.xml")
            for _el in _sm.iter():
                if _el.tag.endswith("loc") and _el.text:
                    _p = urlparse(_el.text.strip())
                    base_url = f"{_p.scheme}://{_p.netloc}"
                    break
        except (OSError, ValueError):
            base_url = ""

    for relative in REQUIRED_FILES:
        if not (site_dir / relative).is_file():
            errors.append(f"missing required file: {relative}")

    # Per-source artifacts grow with the archive — every source with a
    # built snapshot must have a feed and latest JSON. (Don't require all
    # configured SOURCES: tests and fresh checkouts may build a subset.)
    try:
        _sources_path = site_dir / "api" / "sources.json"
        if _sources_path.is_file():
            import json as _json

            _built = _json.loads(_sources_path.read_text(encoding="utf-8"))
            _built_keys = {
                s.get("source")
                for s in _built
                if isinstance(s, dict) and s.get("source")
            }
            for _key in sorted(_built_keys):
                if not (site_dir / f"feed-{_key}.rss").is_file():
                    errors.append(f"missing required file: feed-{_key}.rss")
                if not (site_dir / "api" / "sources" / f"{_key}.json").is_file():
                    errors.append(f"missing required file: api/sources/{_key}.json")
                if not list((site_dir / "static" / "og" / _key).glob("*.png")):
                    errors.append(f"missing OG cards: static/og/{_key}/*.png")
    except (OSError, ValueError):
        pass

    for relative in (
        "manifest.json",
        "api/digest.json",
        "api/sources.json",
        "api/stories.json",
        "api/search.json",
        "api/stats.json",
        "api/trends.json",
        "api/fetch-status.json",
        "api/dead-links.json",
    ):
        path = site_dir / relative
        if path.is_file():
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                errors.append(f"invalid JSON {relative}: {exc}")

    for source_json in sorted((site_dir / "api" / "sources").glob("*.json")):
        try:
            json.loads(source_json.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            errors.append(f"invalid JSON api/sources/{source_json.name}: {exc}")

    if not list((site_dir / "static" / "og" / "home").glob("*.png")):
        errors.append("missing OG cards: static/og/home/*.png")

    for shard in sorted((site_dir / "api").glob("search-*.json")):
        try:
            json.loads(shard.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            errors.append(f"invalid JSON api/{shard.name}: {exc}")

    feed = site_dir / "feed.rss"
    if feed.is_file():
        try:
            _check_rss(feed, errors)
        except (OSError, ElementTree.ParseError) as exc:
            errors.append(f"invalid RSS feed: {exc}")
    for source_feed in sorted(site_dir.glob("feed-*.rss")):
        try:
            _check_rss(source_feed, errors)
        except (OSError, ElementTree.ParseError):
            errors.append(f"invalid RSS feed: {source_feed.name}")

    sitemap = site_dir / "sitemap.xml"
    if sitemap.is_file():
        try:
            root = ElementTree.fromstring(sitemap.read_bytes())
            # Validate every <loc> resolves to a built page.
            for loc in root.iter():
                if not loc.tag.endswith("loc") or not loc.text:
                    continue
                url = loc.text.strip()
                parsed = urlparse(url)
                path = parsed.path or "/"
                bp = base_path.rstrip("/")
                if bp and (path == bp or path.startswith(bp + "/")):
                    path = path[len(bp) :] or "/"
                rel = path.lstrip("/")
                target = site_dir / rel if rel else site_dir / "index.html"
                if target.is_dir():
                    target = target / "index.html"
                if not target.is_file():
                    errors.append(f"sitemap points to missing page: {url}")
        except (OSError, ElementTree.ParseError) as exc:
            errors.append(f"invalid sitemap.xml: {exc}")

    # Feed XSL must ship alongside feeds or browsers show raw XML.
    if (
        list(site_dir.glob("feed*.rss"))
        and not (site_dir / "static" / "feed.xsl").is_file()
    ):
        errors.append("missing required file: static/feed.xsl (referenced by feeds)")

    manifest_path = site_dir / "manifest.json"
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            manifest = None
        if manifest is not None:
            # Manifest icon targets are not HTML href/src attributes, so the
            # link crawl below never sees them — yet a missing icon breaks
            # PWA installability silently. Check them explicitly.
            icons = manifest.get("icons") or []
            if not icons:
                errors.append("manifest.json defines no icons")
            for icon in icons:
                src = icon.get("src") if isinstance(icon, dict) else None
                if not src:
                    errors.append("manifest.json has an icon without src")
                    continue
                # Icon srcs are site-root-relative ("./static/…"); resolve them
                # the same way instead of stripping characters.
                rel = src[2:] if src.startswith("./") else src.lstrip("/")
                target = (site_dir / rel).resolve()
                try:
                    target.relative_to(site_dir.resolve())
                except ValueError:
                    errors.append(f"manifest icon escapes site: {src!r}")
                    continue
                if not target.is_file():
                    errors.append(f"manifest icon missing from site: {src!r}")

    parser = LinkParser()
    for html_file in sorted(site_dir.rglob("*.html")):
        try:
            parser.feed_file(html_file)
        except OSError as exc:
            errors.append(f"could not read {html_file.relative_to(site_dir)}: {exc}")

    for source, reference in parser.references:
        try:
            target = _local_target(reference, source, site_dir, base_path, base_url)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if target is not None and not _exists_as_page(target):
            errors.append(
                f"broken local reference {reference!r} in {source.relative_to(site_dir)}"
            )

    sw = site_dir / "sw.js"
    if sw.is_file():
        sw_text = sw.read_text(encoding="utf-8")
        # Inspect only the PRECACHE array, not the whole worker (its offline
        # fallback references ./ regardless of what it precaches).
        import re

        match = re.search(r"PRECACHE = \[(.*?)\];", sw_text, re.DOTALL)
        precache = match.group(1) if match else ""
        # Precaches the stable app shell plus tiny health data; the daily
        # digest, feed, search index, and other API data revalidate on demand
        # instead, so the SW cache never churns on the daily refresh and
        # first-time visitors don't download the whole search index.
        if '"./static/style.css"' not in precache:
            errors.append("service worker does not precache static/style.css")
        if '"./api/fetch-status.json"' not in precache:
            errors.append(
                "service worker should precache offline health file ./api/fetch-status.json"
            )
        if '"./api/search.json"' in precache:
            errors.append(
                "service worker should lazy-fetch ./api/search.json, not precache it"
            )
        for rel in ("./api/digest.json", "./feed.rss"):
            if f'"{rel}"' in precache:
                errors.append(f"service worker should not precache mutable file {rel}")
        # NOTE: api/index.html embeds the latest sample story (daily) but
        # stays precached as app shell per existing tests; sitemap.xml is
        # never precached (mutable) so a hit here means a build regression.
        for rel in ("./sitemap.xml",):
            if f'"{rel}"' in precache:
                errors.append(f"service worker should not precache mutable file {rel}")
        # NOTE: "./index.html" is intentionally NOT precached (mutable daily
        # digest) — the network-first handler runtime-caches it on first
        # online visit.
        # Every precached URL must exist, or cache.addAll() rejects install.
        for token in re.findall(r'"(\./[^"]+)"', precache):
            rel = token[2:]
            if rel.endswith("/"):
                target = site_dir / rel / "index.html"
            else:
                target = site_dir / rel
            if not target.is_file():
                errors.append(f"service worker precaches missing file: {token}")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a generated catnews site.")
    parser.add_argument("--site", type=Path, default=Path("site"))
    parser.add_argument(
        "--base-path", default="", help="Pages URL prefix, e.g. /catnews"
    )
    parser.add_argument("--base-url", default="", help="Canonical site URL")
    args = parser.parse_args()
    errors = check_site(args.site, args.base_path, args.base_url)
    if errors:
        for error in errors:
            print(f"[catnews] ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
    print(f"[catnews] static site check passed: {args.site}")


if __name__ == "__main__":
    main()
