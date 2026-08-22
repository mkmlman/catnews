from __future__ import annotations

from urllib.parse import urlsplit

# Hosts that serve HTTPS but whose feeds/APIs still hand out http:// links
# (arXiv's Atom <id> is famously http://). Upgraded here so every fetcher,
# curated link, and stored snapshot benefits from the same rule.
HTTPS_ONLY_HOSTS = {"arxiv.org", "www.arxiv.org"}


def safe_http_url(value: str | None, fallback: str | None = None) -> str | None:
    """Return ``value`` only if it is an absolute http(s) URL, else ``fallback``.

    Story links come from third-party feeds and user-submitted content, so an
    unguarded ``javascript:``/``data:``/relative URL would otherwise leak into
    story cards, the API, and the RSS feed. Normalizing here at fetch time is
    the single point of control for both the static build and dev server.
    URLs on HTTPS-only hosts (see ``HTTPS_ONLY_HOSTS``) are upgraded to https.
    """
    if not value:
        return fallback
    value = value.strip()
    try:
        parts = urlsplit(value)
        scheme = parts.scheme.lower()
        host = (parts.hostname or "").lower()
    except ValueError:
        return fallback
    if scheme == "http" and host in HTTPS_ONLY_HOSTS:
        return f"https://{value[7:]}"
    if scheme in ("http", "https"):
        return value
    return fallback
