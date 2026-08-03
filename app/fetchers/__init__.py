from __future__ import annotations

from collections.abc import Awaitable, Callable

import httpx

from ..models import Story

FetchFn = Callable[[httpx.AsyncClient], Awaitable[list[Story]]]


async def fetch_all(
    client, fetchers: dict[str, FetchFn], limits: dict[str, int]
) -> list[Story]:
    """Run all fetchers concurrently and interleave stories by source order."""
    import asyncio

    results = await asyncio.gather(
        *(fn(client) for fn in fetchers.values()), return_exceptions=True
    )
    stories: list[Story] = []
    for (source, _fn), result in zip(fetchers.items(), results):
        if isinstance(result, BaseException):
            print(f"[catnews] fetcher {source!r} failed: {result}")
            continue
        stories.extend(result[: limits.get(source, 50)])
    return stories
