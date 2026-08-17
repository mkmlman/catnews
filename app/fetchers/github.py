from __future__ import annotations

from datetime import datetime, timedelta

from ..config import REQUEST_TIMEOUT, USER_AGENT, today_utc
from ..models import Story
from .sanitize import safe_http_url

GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"

MAX_DESC_CHARS = 900


async def fetch_github(client) -> list[Story]:
    """Fetch popular repos created in the last week via the GitHub search API."""
    since = (today_utc() - timedelta(days=7)).isoformat()
    params = {
        "q": f"created:>{since}",
        "sort": "stars",
        "order": "desc",
        "per_page": 40,
    }
    headers = {"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT}
    response = await client.get(
        GITHUB_SEARCH_URL, params=params, headers=headers, timeout=REQUEST_TIMEOUT
    )
    response.raise_for_status()
    items = response.json().get("items", [])
    return [parse_item(item) for item in items if item.get("full_name")]


def parse_item(item: dict) -> Story:
    full_name = item["full_name"]
    desc = (item.get("description") or "").strip() or None
    return Story(
        source="github",
        title=full_name,
        url=safe_http_url(item.get("html_url")) or f"https://github.com/{full_name}",
        byline=item.get("owner", {}).get("login"),
        author=item.get("owner", {}).get("login"),
        external_id=full_name,
        score=item.get("stargazers_count"),
        snippet=desc[:MAX_DESC_CHARS] if desc else None,
        published=parse_created_at(item.get("created_at")),
    )


def parse_created_at(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
