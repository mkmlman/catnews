from __future__ import annotations

from datetime import datetime

from ..config import REQUEST_TIMEOUT, USER_AGENT
from ..models import Story

ALGOLIA_URL = "https://hn.algolia.com/api/v1/search"

MAX_SNIPPET_CHARS = 900


async def fetch_hn(client) -> list[Story]:
    """Fetch front-page stories from Hacker News via the Algolia API."""
    params = {
        "tags": "front_page",
        "hitsPerPage": 60,
        "query": "",
    }
    response = await client.get(ALGOLIA_URL, params=params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    hits = response.json().get("hits", [])
    return [parse_hit(h) for h in hits if h.get("title")]


def parse_hit(hit: dict) -> Story:
    external_id = str(hit.get("objectID", ""))
    url = hit.get("url") or f"https://news.ycombinator.com/item?id={external_id}"
    author = hit.get("author") or "unknown"
    snippet = (hit.get("story_text") or "").strip() if hit.get("story_text") else None
    return Story(
        source="hn",
        title=hit["title"],
        url=url,
        byline=author,
        external_id=external_id,
        author=author,
        score=hit.get("points"),
        points=hit.get("points"),
        comments=hit.get("num_comments"),
        num_comments=hit.get("num_comments"),
        hn_url=f"https://news.ycombinator.com/item?id={external_id}",
        snippet=snippet[:MAX_SNIPPET_CHARS] if snippet else None,
        published=parse_created_at(hit.get("created_at")),
    )


def parse_created_at(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
