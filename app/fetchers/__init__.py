from __future__ import annotations

from collections.abc import Awaitable, Callable

import httpx

from ..models import Story
from .arxiv import fetch_arxiv
from .github import fetch_github
from .hn import fetch_hn
from .rss import fetch_rss

FetchFn = Callable[[httpx.AsyncClient], Awaitable[list[Story]]]

# Dedicated fetchers shipped with catnews, keyed by source key. rss-type
# sources use the generic feed fetcher instead; everything else (JSON APIs
# like HN/GitHub) resolves here.
API_FETCHERS: dict[str, FetchFn] = {
    "hn": fetch_hn,
    "arxiv": fetch_arxiv,
    "github": fetch_github,
}


def get_fetcher(cfg: dict) -> FetchFn:
    """Resolve the fetcher for a source config dict.

    type: "rss"     -> generic feed fetcher bound to the source's feed URL,
                       honoring optional url_filter / extract_links options
    type: "builtin" -> the dedicated fetcher shipped in app/fetchers/ for this
                       source key (JSON APIs like HN/GitHub)
    """
    if cfg.get("type") == "rss":
        url = cfg["url"]
        source = cfg["key"]
        url_filter = cfg.get("url_filter")
        extract_links = bool(cfg.get("extract_links"))

        async def _fetch(client) -> list[Story]:
            return await fetch_rss(
                client,
                url,
                source,
                url_filter=url_filter,
                extract_links=extract_links,
            )

        return _fetch
    try:
        return API_FETCHERS[cfg["key"]]
    except KeyError:
        raise KeyError(
            f"No built-in fetcher for source {cfg['key']!r}; "
            "use type: rss with a feed url instead."
        ) from None
