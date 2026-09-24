from __future__ import annotations

import os
from datetime import datetime, timedelta

from ..config import REQUEST_TIMEOUT, USER_AGENT, today_utc
from ..models import Story
from .sanitize import safe_http_url

GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"

MAX_DESC_CHARS = 900
MAX_TITLE_CHARS = 140


def display_title(full_name: str, desc: str | None) -> str:
    """A readable card title: ``name — description`` instead of a bare repo path.

    Falls back to ``owner/name`` when the API returns no description.
    """
    name = full_name.rsplit("/", 1)[-1]
    if not desc:
        return full_name
    title = f"{name} — {desc}"
    if len(title) <= MAX_TITLE_CHARS:
        return title
    return title[: MAX_TITLE_CHARS - 1].rstrip() + "…"


async def fetch_github(client) -> list[Story]:
    """Fetch popular repos created in the last week via the GitHub search API.

    Uses ``CATNEWS_GITHUB_TOKEN`` / ``GITHUB_TOKEN`` when set (5000 req/hr
    instead of 60 unauthenticated). Logs whether the request is
    authenticated without ever printing the token.
    """
    since = (today_utc() - timedelta(days=7)).isoformat()
    params = {
        "q": f"created:>{since}",
        "sort": "stars",
        "order": "desc",
        "per_page": 40,
    }
    headers = {"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT}
    token = os.environ.get("CATNEWS_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = await client.get(
        GITHUB_SEARCH_URL, params=params, headers=headers, timeout=REQUEST_TIMEOUT
    )
    if response.status_code == 403 and "rate limit" in response.text.lower():
        print(
            "[catnews] github rate limited (authenticated: "
            f"{bool(token)}); set CATNEWS_GITHUB_TOKEN to raise the quota"
        )
    response.raise_for_status()
    payload = response.json()
    if payload.get("incomplete_results"):
        print("[catnews] warning: github search returned incomplete_results")
    items = payload.get("items", [])
    return [parse_item(item) for item in items if item.get("full_name")]


def parse_item(item: dict) -> Story:
    full_name = item["full_name"]
    desc = (item.get("description") or "").strip() or None
    return Story(
        source="github",
        title=display_title(full_name, desc),
        url=safe_http_url(item.get("html_url")) or f"https://github.com/{full_name}",
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
