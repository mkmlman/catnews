from __future__ import annotations

from urllib.parse import urlsplit


def safe_http_url(value: str | None, fallback: str | None = None) -> str | None:
    """Return ``value`` only if it is an absolute http(s) URL, else ``fallback``.

    Story links come from third-party feeds and user-submitted content, so an
    unguarded ``javascript:``/``data:``/relative URL would otherwise leak into
    story cards, the API, and the RSS feed. Normalizing here at fetch time is
    the single point of control for both the static build and dev server.
    """
    if not value:
        return fallback
    value = value.strip()
    try:
        scheme = urlsplit(value).scheme.lower()
    except ValueError:
        return fallback
    if scheme in ("http", "https"):
        return value
    return fallback
