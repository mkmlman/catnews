from __future__ import annotations

import html as html_lib
import re
from datetime import UTC, datetime
from urllib.parse import urlparse

import feedparser

from ..config import REQUEST_TIMEOUT
from ..models import CuratedLink, Story
from .sanitize import safe_http_url

MAX_SNIPPET_CHARS = 900
MAX_LINKS = 30
MAX_LINK_TITLE_CHARS = 64

# Social hosts where bare profile/handle links are treated as inline mentions
# rather than curated content (status/post links are still kept).
_SOCIAL_HOSTS = {"x.com", "twitter.com", "bsky.app", "mastodon.social"}


def strip_html(value: str) -> str:
    """Strip tags/entities from an RSS summary and collapse whitespace."""
    text = html_lib.unescape(re.sub(r"<[^>]+>", " ", value or ""))
    return re.sub(r"\s+", " ", text).strip()


def _published(entry) -> datetime | None:
    if entry.get("published_parsed"):
        return datetime(*entry["published_parsed"][:6], tzinfo=UTC)
    if entry.get("updated_parsed"):
        return datetime(*entry["updated_parsed"][:6], tzinfo=UTC)
    return None


def parse_entry(
    entry, source: str, *, url_filter: str | None = None, feed_author: str | None = None
) -> Story | None:
    url = entry.get("link")
    title = entry.get("title")
    if not title or not url:
        return None
    url = safe_http_url(url)
    if url is None:
        return None
    if url_filter and url_filter not in url:
        return None

    snippet = entry.get("summary") or entry.get("description") or ""

    content = ""
    if entry.get("content"):
        content = entry.get("content")[0].get("value", "")
    if not snippet and content:
        snippet = content

    # Atom feeds (e.g. Simon Willison) often declare the author once at the
    # feed level instead of on every entry; fall back to that when needed.
    author = entry.get("author") or feed_author
    external_id = entry.get("id") or url.rstrip("/").split("/")[-1]

    return Story(
        source=source,
        title=title.strip(),
        url=url,
        byline=author,
        author=author,
        external_id=external_id,
        published=_published(entry),
        snippet=(strip_html(snippet)[:MAX_SNIPPET_CHARS] or None),
    )


def _root_domain(host: str) -> str:
    """Last two labels of a host, covering arbitrary subdomains (tools., static.)."""
    parts = host.removeprefix("www.").split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def parse_links(content: str, *, self_host: str | None = None) -> list[CuratedLink]:
    """Extract the links curated inside a post, attributed to their origin sites.

    Links back to the publisher's own site (self_host) are internal navigation,
    not curated content, so they're dropped.
    """
    links: list[CuratedLink] = []
    seen: set[str] = set()
    root = _root_domain(self_host) if self_host else ""
    for match in re.finditer(
        r"""<a\b[^>]*?(?:href=(?:"([^"]*)"|'([^']*)'))[^>]*>(.*?)</a>""",
        content,
        re.DOTALL,
    ):
        if len(links) >= MAX_LINKS:
            break
        url = html_lib.unescape(match.group(1) or match.group(2) or "").strip()
        text = _anchor_text(match.group(3))
        if not url or len(text) < 3:
            continue
        if safe_http_url(url) is None:
            continue
        host = urlparse(url).netloc.lower()
        if root and (_root_domain(host) == root or host == (self_host or "").lower()):
            continue
        if _is_social_profile(url, host):
            continue
        # Skip the newsletter's own CDN/host links — image assets and self
        # links are never curated content.
        if "substackcdn" in host:
            continue
        if url in seen:
            continue
        seen.add(url)
        links.append(
            CuratedLink(
                title=text[:MAX_LINK_TITLE_CHARS].rstrip(),
                url=url,
                site=host.removeprefix("www.") or None,
            )
        )
    return links


def _anchor_text(fragment: str) -> str:
    """Strip tags/entities from an anchor's inner HTML and collapse whitespace."""
    text = html_lib.unescape(re.sub(r"<[^>]+>", " ", fragment))
    return re.sub(r"\s+", " ", text).strip()


def _is_social_profile(url: str, host: str) -> bool:
    """Skip bare profile/handle links (e.g. x.com/username) that are inline
    mentions rather than curated content, but keep status/post links."""
    if host not in _SOCIAL_HOSTS:
        return False
    parts = [p for p in urlparse(url).path.split("/") if p]
    return bool(len(parts) <= 2 and "status" not in parts)


def _entry_links(
    entry, extract_links: bool, *, self_host: str | None = None
) -> list[CuratedLink]:
    if not extract_links:
        return []
    # Some feeds ship links in <content:encoded> (Substack), others only in
    # the summary (Atom, e.g. Simon Willison) — try both.
    content = ""
    if entry.get("content"):
        content = entry.get("content")[0].get("value", "")
    if not content:
        content = entry.get("summary") or ""
    return parse_links(content, self_host=self_host)


async def fetch_rss(
    client,
    url: str,
    source: str,
    *,
    url_filter: str | None = None,
    extract_links: bool = False,
) -> list[Story]:
    """Fetch any blog/newsletter feed and map entries to Story objects.

    Covers Substack (/feed), Ghost, WordPress, Bear, and any standard RSS/Atom
    feed. Optional per-source behaviors:

      url_filter    only keep entries whose URL contains this substring
                    (e.g. "joy-and-curiosity" for the Register Spill series)
      extract_links parse the links curated inside each post into Story.links

    """
    response = await client.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    parsed = feedparser.parse(response.content)
    feed_author = parsed.feed.get("author")
    self_host = urlparse(url).netloc.lower()
    stories: list[Story] = []
    for entry in parsed.entries:
        story = parse_entry(
            entry, source, url_filter=url_filter, feed_author=feed_author
        )
        if story:
            story.links = _entry_links(entry, extract_links, self_host=self_host)
            stories.append(story)
    return stories
