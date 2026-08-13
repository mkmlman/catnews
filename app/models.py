from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class Source(str):
    """Valid source key: lowercase alphanumerics with underscores.

    Sources are user-configurable via sources.yaml, so this stays a loose
    pattern rather than a fixed enumeration; pydantic applies it to the
    `source` fields below.
    """

    _pattern = "^[a-z0-9_]+$"


class CuratedLink(BaseModel):
    """A link curated inside a story (e.g. a Register Spill newsletter post)."""

    title: str = Field(description="Anchor text / title of the linked item")
    url: str
    site: str | None = Field(
        default=None, description="Origin site (hostname) for attribution"
    )


class Story(BaseModel):
    """A single curated story in a digest."""

    source: str = Field(
        description="Where the story came from: hn | arxiv | github",
        pattern=Source._pattern,
    )
    title: str
    url: str
    author: str | None = None
    byline: str | None = Field(
        default=None,
        description="Short attribution shown next to the source, e.g. the HN submitter",
    )
    external_id: str | None = Field(
        default=None, description="Native id in the source system"
    )
    summary: str | None = Field(
        default=None, description="Short digestible summary of the story"
    )
    why_read: str | None = Field(
        default=None, description="Curation note: why this story is worth your time"
    )
    authors: list[str] = Field(
        default_factory=list, description="Full author list (arXiv)"
    )
    category: str | None = Field(
        default=None, description="Primary category (arXiv), e.g. cs.LG"
    )
    published: datetime | None = None
    score: int | None = None
    comments: int | None = None
    hn_url: str | None = None
    points: int | None = None
    num_comments: int | None = None
    snippet: str | None = Field(
        default=None, description="Plain-text excerpt of the story"
    )
    links: list[CuratedLink] = Field(
        default_factory=list,
        description="Curated links inside the story, credited to their origin sites",
    )

    def to_markdown(self) -> str:
        """Render the story as a markdown block (matches the /api/story md output)."""
        author = self.author or "unknown"
        lines = [f"By {author}"]
        if self.why_read:
            lines.append(f"**Why read:** {self.why_read}")
        if self.authors:
            lines.append(f"**Authors:** {', '.join(self.authors)}")
        lines.append(f"## [{self.title}]({self.url})")
        if self.summary:
            lines.append(self.summary)
        return "\n\n".join(lines)


class Digest(BaseModel):
    """One day's edition of the digest (legacy: combined sources)."""

    date: date
    stories: list[Story]

    @property
    def stats(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for story in self.stories:
            counts[story.source] = counts.get(story.source, 0) + 1
        return counts


class SourceSnapshot(BaseModel):
    """One fetch of a single source, archived under data/source_<name>_<date>.json."""

    source: str = Field(pattern=Source._pattern)
    date: date
    stories: list[Story]


class SiteStats(BaseModel):
    total_stories: int
    editions: int
    first_edition: date | None
    last_edition: date | None
    by_source: dict[str, int]
    snapshots_by_source: dict[str, int] = {}
