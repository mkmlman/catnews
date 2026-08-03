from __future__ import annotations

from datetime import UTC, datetime

import feedparser

from ..config import REQUEST_TIMEOUT
from ..models import Story

FEED_URL = "https://registerspill.thorstenball.com/feed"

# Only keep posts from the "Joy & Curiosity" series (the topic the newsletter
# section is dedicated to). Slugs look like "joy-and-curiosity-93".
SERIES_SLUG = "joy-and-curiosity"

MAX_SNIPPET_CHARS = 900


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
    )
