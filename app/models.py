from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class Source(str):
    """Enumerated source label for a story."""


class Story(BaseModel):
    """A single curated story in a digest."""

    source: str = Field(description="Where the story came from: hn | arxiv | github")
    title: str
    url: str
    author: str | None = None
    byline: str | None = Field(
        default=None, description="Short attribution shown next to the source, e.g. the HN submitter"
    )
    external_id: str | None = Field(default=None, description="Native id in the source system")
    summary: str | None = Field(default=None, description="Short digestible summary of the story")
    why_read: str | None = Field(default=None, description="Curation note: why this story is worth your time")
    signal: str = Field(default="All", description="All | Recommended | Must-Read")
    authors: list[str] = Field(default_factory=list, description="Full author list (arXiv)")
    published: datetime | None = None
    score: int | None = None
    comments: int | None = None
    hn_url: str | None = None
    points: int | None = None
    num_comments: int | None = None
    snippet: str | None = Field(default=None, description="Plain-text excerpt of the story")

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
    """One day's edition of the digest."""

    date: date
    stories: list[Story]

    @property
    def stats(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for story in self.stories:
            counts[story.source] = counts.get(story.source, 0) + 1
        return counts


class SiteStats(BaseModel):
    total_stories: int
    editions: int
    first_edition: date | None
    last_edition: date | None
    by_source: dict[str, int]
    by_signal: dict[str, int]
