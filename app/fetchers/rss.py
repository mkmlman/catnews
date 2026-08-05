from __future__ import annotations

import html as html_lib
import re
from datetime import UTC, datetime

import feedparser

from ..config import REQUEST_TIMEOUT
from ..models import Story

MAX_SNIPPET_CHARS = 900


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


def parse_entry(entry, source: str) -> Story | None:
    url = entry.get("link")
    title = entry.get("title")
    if not title or not url:
        return None

    snippet = entry.get("summary") or entry.get("description") or ""

    content = ""
    if entry.get("content"):
        content = entry.get("content")[0].get("value", "")
    if not snippet and content:
        snippet = content

    author = entry.get("author")
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


async def fetch_rss(client, url: str, source: str) -> list[Story]:
    """Fetch any blog/newsletter feed and map entries to Story objects.

    Covers Substack (/feed), Ghost, WordPress, Bear, and any standard RSS/Atom
    feed — the same generic fetcher serves every rss-type source.
    """
    response = await client.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    parsed = feedparser.parse(response.content)
    stories = [parse_entry(entry, source) for entry in parsed.entries]
    return [s for s in stories if s]
