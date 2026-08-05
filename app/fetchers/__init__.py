from __future__ import annotations

from collections.abc import Awaitable, Callable

import httpx

from ..models import Story
from .arxiv import fetch_arxiv
from .github import fetch_github
from .hn import fetch_hn
from .registerspill import fetch_registerspill
from .rss import fetch_rss

FetchFn = Callable[[httpx.AsyncClient], Awaitable[list[Story]]]

# Built-in API fetchers, keyed by source key. Any source with type != "rss"
# resolves here; rss-type sources use the generic feed fetcher instead.
API_FETCHERS: dict[str, FetchFn] = {
    "hn": fetch_hn,
    "arxiv": fetch_arxiv,
    "github": fetch_github,
    "registerspill": fetch_registerspill,
}


def get_fetcher(cfg: dict) -> FetchFn:
    """Resolve the fetcher for a source config dict.

    type: "rss"  -> generic feed fetcher bound to the source's feed URL
    type: "api"  -> the built-in fetcher for the source key
    """
    if cfg.get("type") == "rss":
        url = cfg["url"]
        source = cfg["key"]

        async def _fetch(client) -> list[Story]:
            return await fetch_rss(client, url, source)

        return _fetch
    try:
        return API_FETCHERS[cfg["key"]]
    except KeyError:
        raise KeyError(
            f"No built-in fetcher for source {cfg['key']!r}; "
            "use type: rss with a feed url instead."
        ) from None
