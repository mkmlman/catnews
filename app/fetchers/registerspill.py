from __future__ import annotations

import html
import re
from datetime import UTC, datetime
from urllib.parse import urlparse

import feedparser

from ..config import REQUEST_TIMEOUT
from ..models import CuratedLink, Story

FEED_URL = "https://registerspill.thorstenball.com/feed"

# Only keep posts from the "Joy & Curiosity" series (the topic the newsletter
# section is dedicated to). Slugs look like "joy-and-curiosity-93".
SERIES_SLUG = "joy-and-curiosity"

MAX_SNIPPET_CHARS = 900
MAX_LINKS = 30


async def fetch_registerspill(client) -> list[Story]:
    """Fetch the latest Register Spill posts via its RSS feed."""
    response = await client.get(FEED_URL, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    parsed = feedparser.parse(response.content)
    stories = [parse_entry(entry) for entry in parsed.entries]
    return [s for s in stories if s]


def parse_entry(entry) -> Story | None:
    url = entry.get("link")
    title = entry.get("title")
    if not title or not url or SERIES_SLUG not in url:
        return None

    author = entry.get("author") or "Thorsten Ball"
    snippet = ""
    if entry.get("summary"):
        snippet = entry.summary
    elif entry.get("description"):
        snippet = entry.description

    published = None
    if entry.get("published_parsed"):
        published = datetime(*entry.published_parsed[:6], tzinfo=UTC)
    elif entry.get("updated_parsed"):
        published = datetime(*entry.updated_parsed[:6], tzinfo=UTC)

    external_id = url.rstrip("/").split("/")[-1]

    content = entry.get("content", [{}])[0].get("value", "")

    return Story(
        source="registerspill",
        title=title.strip(),
        url=url,
        byline=author,
        author=author,
        external_id=external_id,
        published=published,
        snippet=(snippet[:MAX_SNIPPET_CHARS] + "…")
        if len(snippet) > MAX_SNIPPET_CHARS
        else snippet or None,
        links=parse_links(content),
    )


def _anchor_text(fragment: str) -> str:
    """Strip tags/entities from an anchor's inner HTML and collapse whitespace."""
    text = html.unescape(re.sub(r"<[^>]+>", " ", fragment))
    return re.sub(r"\s+", " ", text).strip()


def _is_social_profile(url: str, host: str) -> bool:
    """Skip bare profile/handle links (e.g. x.com/username) that are inline
    mentions rather than curated content, but keep status/post links."""
    if host not in {"x.com", "twitter.com", "bsky.app", "mastodon.social"}:
        return False
    parts = [p for p in urlparse(url).path.split("/") if p]
    return bool(len(parts) <= 2 and "status" not in parts)


def parse_links(content: str) -> list[CuratedLink]:
    """Extract the links curated inside a post, attributed to their origin sites."""
    links: list[CuratedLink] = []
    seen: set[str] = set()
    for match in re.finditer(
        r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', content, re.DOTALL
    ):
        if len(links) >= MAX_LINKS:
            break
        url = html.unescape(match.group(1)).strip()
        text = _anchor_text(match.group(2))
        if not url or len(text) < 3:
            continue
        if url.startswith(("mailto:", "tel:")):
            continue
        host = urlparse(url).netloc.lower()
        if host == "registerspill.thorstenball.com" or "substack" in host:
            continue
        if _is_social_profile(url, host):
            continue
        if url in seen:
            continue
        seen.add(url)
        links.append(
            CuratedLink(
                title=text,
                url=url,
                site=host.removeprefix("www.") or None,
            )
        )
    return links
