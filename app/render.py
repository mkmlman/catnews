from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from feedgen.feed import FeedGenerator
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import APP_NAME
from .models import Digest

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

CAT = r"""  /\_/\
 (=^.^=)
 (")_(")"""

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=select_autoescape(["html"])
)


def render_page(name: str, *, base_path: str, base_url: str, **context) -> str:
    """Render a template to a full HTML string. Works for the live app and static builds."""
    template = _env.get_template(name)
    return template.render(
        app_name=APP_NAME,
        base_path=base_path,
        base_url=base_url,
        cat=CAT,
        **context,
    )


def render_markdown(digest: Digest) -> str:
    blocks = [
        f"# {APP_NAME} — {digest.date}",
        "",
    ]
    for i, story in enumerate(digest.stories, 1):
        blocks.append(f"### {i}. {story.title}")
        blocks.append("")
        blocks.append(
            f"- **Source:** {story.source} · **By:** {story.byline or story.author or 'unknown'}"
        )
        if story.why_read:
            blocks.append(f"- **Why read:** {story.why_read}")
        blocks.append(f"- **Link:** {story.url}")
        blocks.append("")
    return "\n".join(blocks)


def _aware(dt) -> datetime:
    """Ensure a datetime carries tzinfo (feedgen requires aware datetimes)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def render_rss(digest: Digest, base_url: str) -> str:
    fg = FeedGenerator()
    fg.id(f"{base_url}/")
    fg.title(APP_NAME)
    fg.link(href=base_url, rel="alternate")
    fg.subtitle("catnews — latest across all sources.")
    fg.language("en")

    for story in digest.stories:
        entry = fg.add_entry()
        entry.id(story.url)
        entry.title(story.title)
        entry.link(href=story.url)
        entry.author({"name": story.byline or story.author or "unknown"})
        if story.published:
            entry.published(_aware(story.published))
        parts = []
        if story.why_read:
            parts.append(f"<p><strong>Why read:</strong> {story.why_read}</p>")
        if story.summary:
            parts.append(f"<p>{story.summary}</p>")
        if story.hn_url:
            parts.append(f'<p>Discuss on <a href="{story.hn_url}">Hacker News</a></p>')
        entry.content("".join(parts), type="html")

    return fg.rss_str(pretty=True).decode("utf-8")
