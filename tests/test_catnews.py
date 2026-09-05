from __future__ import annotations

import asyncio
import re
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from app.fetchers.arxiv import parse_entry
from app.fetchers.github import parse_item
from app.fetchers.hn import parse_hit
from app.fetchers.rss import parse_entry as parse_rss_entry
from app.fetchers.rss import parse_links, strip_html
from app.models import CuratedLink, SourceSnapshot, Story
from app.render import live_site_urls, search_index, site_version
from app.store import (
    arxiv_category_counts,
    combined_digest,
    days_archiving,
    fetch_health,
    fetch_status,
    latest_stories_by_source,
    load_all_snapshots,
    save_fetch_report,
    save_snapshot,
    site_stats,
    source_registry,
    top_domains,
    unseen_stories,
    weekly_trends,
)
from scripts.fetch_digest import due_sources

SAMPLE_HIT = {
    "objectID": "49138188",
    "title": "Diátaxis",
    "url": "https://diataxis.fr/",
    "author": "ryanseys",
    "points": 120,
    "num_comments": 42,
    "story_text": "A systematic approach to documentation.",
    "created_at": "2026-07-29T09:00:00.000Z",
}


def test_hn_parse_hit():
    story = parse_hit(SAMPLE_HIT)
    assert story.source == "hn"
    assert story.title == "Diátaxis"
    assert story.url == "https://diataxis.fr/"
    assert story.hn_url == "https://news.ycombinator.com/item?id=49138188"
    assert story.score == 120
    assert story.snippet == "A systematic approach to documentation."


def test_hn_parse_hit_no_url_uses_hn_item():
    hit = {**SAMPLE_HIT, "url": None}
    story = parse_hit(hit)
    assert story.url == "https://news.ycombinator.com/item?id=49138188"


ARXIV_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2607.28628v1</id>
    <published>2026-07-29T17:00:00Z</published>
    <title>Learning to Trace Seiberg Dualities</title>
    <author><name>Jonathan J. Heckman</name></author>
    <author><name>Shani Meynet</name></author>
    <summary>We study tracing via local models.</summary>
    <arxiv:primary_category term="hep-th"/>
  </entry>
</feed>"""


def test_arxiv_parse_entry():
    import xml.etree.ElementTree as ET

    root = ET.fromstring(ARXIV_XML)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entry = root.find("atom:entry", ns)
    assert entry is not None
    story = parse_entry(entry)
    assert story is not None
    assert story.source == "arxiv"
    assert story.external_id == "2607.28628v1"
    assert story.authors == ["Jonathan J. Heckman", "Shani Meynet"]
    assert story.url == "https://arxiv.org/abs/2607.28628v1"
    assert story.category == "hep-th"


def test_github_parse_item():
    item = {
        "full_name": "MoonshotAI/Kimi-K3",
        "html_url": "https://github.com/MoonshotAI/Kimi-K3",
        "description": "A 2.78T parameter model.",
        "stargazers_count": 9999,
        "owner": {"login": "MoonshotAI"},
        "created_at": "2026-07-20T00:00:00Z",
    }
    story = parse_item(item)
    assert story.source == "github"
    assert story.title == "Kimi-K3 — A 2.78T parameter model."
    assert story.score == 9999


def test_github_parse_item_title_fallback_and_truncation():
    from app.fetchers.github import MAX_TITLE_CHARS

    no_desc = parse_item(
        {
            "full_name": "MengTo/threeui",
            "description": None,
            "owner": {"login": "MengTo"},
        }
    )
    assert no_desc.title == "MengTo/threeui"

    long_desc = "x" * 300
    truncated = parse_item(
        {
            "full_name": "a/repo",
            "description": long_desc,
            "owner": {"login": "a"},
        }
    )
    assert len(truncated.title) == MAX_TITLE_CHARS
    assert truncated.title.endswith("…")
    assert truncated.title.startswith("repo — ")


def test_registerspill_parse_links():
    body = (
        '<p>Re-read <a href="https://sahillavingia.com/reflecting">Reflecting on My Failure</a>.</p>'
        '<p>Met <a href="https://x.com/adamwathan">Adam</a> in person.</p>'
        '<a href="https://x.com/jeremygiffon/status/123">Grip Strength</a>'
        '<a href="https://substackcdn.com/image/1">img</a>'
    )
    links = parse_links(body)
    titles = [l.title for l in links]
    assert "Reflecting on My Failure" in titles
    assert "Grip Strength" in titles
    assert "Adam" not in titles
    assert all(l.site for l in links)
    assert all("substackcdn" not in l.url for l in links)


def test_rss_url_filter_keeps_only_matching_entries():
    joy = {
        "link": "https://registerspill.thorstenball.com/p/joy-and-curiosity-93",
        "title": "Joy & Curiosity #93",
    }
    other = {
        "link": "https://registerspill.thorstenball.com/p/ownership",
        "title": "Ownership",
    }
    assert (
        parse_rss_entry(joy, "registerspill", url_filter="joy-and-curiosity")
        is not None
    )
    assert (
        parse_rss_entry(other, "registerspill", url_filter="joy-and-curiosity") is None
    )


def test_rss_parse_entry():
    entry = {
        "title": "On child birth",
        "link": "https://www.henrikkarlsson.xyz/p/child-birth",
        "author": "Henrik Karlsson",
        "summary": "<p>Some <b>html</b> summary.</p>",
        "published_parsed": (2026, 7, 29, 9, 55, 8, 2, 210, 0),
        "id": "https://www.henrikkarlsson.xyz/p/child-birth",
    }
    story = parse_rss_entry(entry, "escflat")
    assert story is not None
    assert story.source == "escflat"
    assert story.title == "On child birth"
    assert story.author == "Henrik Karlsson"
    assert story.external_id == "https://www.henrikkarlsson.xyz/p/child-birth"
    assert story.published is not None
    assert story.snippet is not None
    assert "html" in story.snippet


def test_rss_parse_entry_skips_missing_link():
    assert parse_rss_entry({"title": "No link"}, "escflat") is None


def test_rss_parse_entry_falls_back_to_feed_author():
    # Atom feeds (Simon Willison) declare the author once at the feed level.
    entry = {"title": "A post", "link": "https://simonwillison.net/2026/Aug/17/a-post/"}
    story = parse_rss_entry(entry, "simonw")
    assert story is not None
    assert story.author is None
    story_with_author = parse_rss_entry(entry, "simonw", feed_author="Simon Willison")
    assert story_with_author is not None
    assert story_with_author.author == "Simon Willison"


def test_rss_strip_html():
    assert strip_html("<p>Hello &amp; <b>world</b></p>") == "Hello & world"
    assert strip_html("") == ""


def test_fetch_rss_extracts_links_when_requested():
    import asyncio

    from app.fetchers.rss import fetch_rss

    feed_xml = (
        "<rss version='2.0'><channel>"
        "<item><title>Joy &amp; Curiosity #93</title>"
        "<link>https://registerspill.thorstenball.com/p/joy-and-curiosity-93</link>"
        "<author>Thorsten Ball</author>"
        "<content:encoded xmlns:content='http://purl.org/rss/1.0/modules/content/'>"
        '<![CDATA[<p>See <a href="https://gwern.net/">gwern</a>.</p>]]>'
        "</content:encoded></item>"
        "<item><title>Ownership</title>"
        "<link>https://registerspill.thorstenball.com/p/ownership</link>"
        "</item>"
        "</channel></rss>"
    )

    class FakeClient:
        async def get(self, url, timeout=None):
            response = SimpleNamespace(content=feed_xml.encode())
            response.raise_for_status = lambda: None
            return response

    async def run():
        return await fetch_rss(
            FakeClient(),
            "https://registerspill.thorstenball.com/feed",
            "registerspill",
            url_filter="joy-and-curiosity",
            extract_links=True,
        )

    stories = asyncio.run(run())
    assert [s.title for s in stories] == ["Joy & Curiosity #93"]
    assert stories[0].source == "registerspill"
    assert [l.title for l in stories[0].links] == ["gwern"]


def test_fetch_rss_extracts_links_and_author_from_atom_summary():
    import asyncio

    from app.fetchers.rss import fetch_rss

    feed_xml = (
        "<?xml version='1.0' encoding='utf-8'?>"
        "<feed xmlns='http://www.w3.org/2005/Atom'>"
        "<title>simonwillison</title>"
        "<author><name>Simon Willison</name></author>"
        "<entry><title>Links worth reading</title>"
        "<link href='https://simonwillison.net/2026/Aug/17/links-worth-reading/'/>"
        "<summary type='html'><![CDATA[<p>Start with "
        "<a href='https://gwern.net/'>gwern</a>, "
        "<a href='https://arxiv.org/'>arXiv</a>, and my "
        "<a href='https://simonwillison.net/tags/ai/'>own tag</a>.</p>]]></summary>"
        "</entry>"
        "</feed>"
    )

    class FakeClient:
        async def get(self, url, timeout=None):
            response = SimpleNamespace(content=feed_xml.encode())
            response.raise_for_status = lambda: None
            return response

    async def run():
        return await fetch_rss(
            FakeClient(),
            "https://simonwillison.net/atom/everything/",
            "simonw",
            extract_links=True,
        )

    stories = asyncio.run(run())
    assert [s.title for s in stories] == ["Links worth reading"]
    assert stories[0].author == "Simon Willison"  # feed-level author fallback
    assert [l.title for l in stories[0].links] == ["gwern", "arXiv"]
    assert stories[0].links[0].site == "gwern.net"
    assert stories[0].links[1].site == "arxiv.org"


def test_story_markdown_and_why_read():
    story = Story(
        source="hn",
        title="T",
        url="https://example.com",
        author="alice",
        why_read="Short.",
    )
    md = story.to_markdown()
    assert "**Why read:** Short." in md
    assert "## [T](https://example.com)" in md


def test_snapshot_store_roundtrip(tmp_path):
    snap = SourceSnapshot(
        source="hn",
        date=date(2026, 8, 2),
        stories=[
            Story(source="hn", title="A", url="https://a"),
            Story(source="hn", title="B", url="https://b"),
        ],
    )
    path = save_snapshot(snap, tmp_path)
    assert path.exists()

    loaded = SourceSnapshot.model_validate_json(path.read_text())
    assert [s.title for s in loaded.stories] == ["A", "B"]

    stats = site_stats(tmp_path)
    assert stats.total_stories == 2
    assert stats.editions == 1
    assert stats.by_source == {"hn": 2}
    assert stats.snapshots_by_source == {"hn": 1}

    latest = latest_stories_by_source(tmp_path)
    assert [s.title for s in latest["hn"]] == ["A", "B"]


def test_snapshot_store_supports_source_keys_with_underscores(tmp_path):
    save_snapshot(
        SourceSnapshot(
            source="my_source",
            date=date(2026, 8, 2),
            stories=[Story(source="my_source", title="A", url="https://a")],
        ),
        tmp_path,
    )

    snapshots = load_all_snapshots(tmp_path)
    assert [(s.source, s.date) for s in snapshots] == [("my_source", date(2026, 8, 2))]
    assert list(latest_stories_by_source(tmp_path)) == ["my_source"]


def test_fetch_one_can_skip_curation(monkeypatch, tmp_path):
    from scripts import fetch_digest

    save_curation = tmp_path / "curation_2026-08-02.json"
    save_curation.write_text('{"stories": {"hn:1": {"why_read": "Curated note"}}}')

    async def fake_fetch(_client):
        return [
            Story(
                source="hn",
                title="A",
                url="https://a",
                external_id="1",
            )
        ]

    monkeypatch.setattr(fetch_digest, "get_fetcher", lambda _cfg: fake_fetch)

    async def run(apply_curation_overrides):
        return await fetch_digest.fetch_one(
            None,
            "hn",
            10,
            date(2026, 8, 2),
            tmp_path,
            apply_curation_overrides=apply_curation_overrides,
        )

    curated = asyncio.run(run(True))
    uncurated = asyncio.run(run(False))
    assert curated.stories[0].why_read == "Curated note"
    assert uncurated.stories[0].why_read is None


def test_fetch_one_retries_transient_http_errors(monkeypatch, tmp_path):
    from scripts import fetch_digest

    calls = 0

    async def flaky_fetch(_client):
        nonlocal calls
        calls += 1
        if calls < 3:
            request = httpx.Request("GET", "https://example.com")
            response = httpx.Response(
                503, request=request, headers={"Retry-After": "0"}
            )
            raise httpx.HTTPStatusError(
                "temporary outage", request=request, response=response
            )
        return [Story(source="hn", title="Recovered", url="https://a")]

    monkeypatch.setattr(fetch_digest, "get_fetcher", lambda _cfg: flaky_fetch)
    monkeypatch.setattr(fetch_digest, "FETCH_ATTEMPTS", 3)
    monkeypatch.setattr(fetch_digest, "FETCH_BACKOFF_SECONDS", 0.0)

    snapshot = asyncio.run(
        fetch_digest.fetch_one(None, "hn", 10, date(2026, 8, 2), tmp_path)
    )
    assert calls == 3
    assert snapshot.stories[0].title == "Recovered"


def test_unseen_stories_filters_prior_snapshots(tmp_path):
    # A rolling feed repeats its recent entries every fetch; unseen_stories
    # keeps only genuinely new stories so consecutive snapshots don't duplicate.
    prior = SourceSnapshot(
        source="simonw",
        date=date(2026, 8, 16),
        stories=[
            Story(
                source="simonw",
                title="Old",
                url="https://sw.net/old",
                external_id="old",
            ),
            Story(source="simonw", title="No id", url="https://sw.net/no-id"),
        ],
    )
    save_snapshot(prior, tmp_path)

    fresh = SourceSnapshot(
        source="simonw",
        date=date(2026, 8, 17),
        stories=[
            Story(
                source="simonw",
                title="Old",
                url="https://sw.net/old",
                external_id="old",
            ),
            Story(source="simonw", title="No id again", url="https://sw.net/no-id"),
            Story(
                source="simonw",
                title="New",
                url="https://sw.net/new",
                external_id="new",
            ),
        ],
    )
    kept = unseen_stories(fresh, tmp_path)
    assert [s.title for s in kept] == ["New"]

    # Stories from other sources are never treated as duplicates.
    other = SourceSnapshot(
        source="hn",
        date=date(2026, 8, 17),
        stories=[
            Story(source="hn", title="HN", url="https://sw.net/old", external_id="old")
        ],
    )
    assert [s.title for s in unseen_stories(other, tmp_path)] == ["HN"]


def test_archive_days_groups_newest_first():
    from app.render import archive_days

    snapshots = [
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 2),
            stories=[Story(source="hn", title="A", url="https://a")],
        ),
        SourceSnapshot(
            source="arxiv",
            date=date(2026, 8, 2),
            stories=[
                Story(source="arxiv", title="P", url="https://b"),
                Story(source="arxiv", title="Q", url="https://c"),
            ],
        ),
        SourceSnapshot(
            source="github",
            date=date(2026, 8, 3),
            stories=[Story(source="github", title="R", url="https://d")],
        ),
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 3),
            stories=[Story(source="hn", title="B", url="https://e")],
        ),
    ]
    days = archive_days(snapshots)
    assert [d["date"] for d in days] == [date(2026, 8, 3), date(2026, 8, 2)]
    assert days[0]["stories"] == 2
    # same-day snapshots are sorted by source
    assert [s.source for s in days[0]["snapshots"]] == ["github", "hn"]
    assert [s.source for s in days[1]["snapshots"]] == ["arxiv", "hn"]
    assert days[1]["stories"] == 3


def test_combined_digest_merges_latest_per_source(tmp_path):
    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 1),
            stories=[Story(source="hn", title="HN1", url="https://a")],
        ),
        tmp_path,
    )
    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 2),
            stories=[Story(source="hn", title="HN2", url="https://a")],
        ),
        tmp_path,
    )
    save_snapshot(
        SourceSnapshot(
            source="arxiv",
            date=date(2026, 8, 2),
            stories=[Story(source="arxiv", title="PAPER", url="https://b")],
        ),
        tmp_path,
    )
    digest = combined_digest(tmp_path)
    assert digest is not None
    assert [s.title for s in digest.stories] == ["HN2", "PAPER"]


def test_combined_digest_interleaves_sources(tmp_path):
    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 2),
            stories=[
                Story(source="hn", title="HN1", url="https://a"),
                Story(source="hn", title="HN2", url="https://a"),
            ],
        ),
        tmp_path,
    )
    save_snapshot(
        SourceSnapshot(
            source="arxiv",
            date=date(2026, 8, 2),
            stories=[Story(source="arxiv", title="PAPER", url="https://b")],
        ),
        tmp_path,
    )
    save_snapshot(
        SourceSnapshot(
            source="github",
            date=date(2026, 8, 2),
            stories=[Story(source="github", title="REPO", url="https://c")],
        ),
        tmp_path,
    )
    digest = combined_digest(tmp_path)
    assert digest is not None
    assert [s.source for s in digest.stories] == ["hn", "arxiv", "github", "hn"]


def test_combined_digest_is_dated_from_newest_snapshot_not_today(tmp_path):
    # A built site must never claim a later date than its own data: when the
    # newest snapshot is Aug 2 but "today" is later, the digest reads Aug 2.
    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 2),
            stories=[Story(source="hn", title="HN", url="https://a")],
        ),
        tmp_path,
    )
    save_snapshot(
        SourceSnapshot(
            source="arxiv",
            date=date(2026, 8, 1),
            stories=[Story(source="arxiv", title="PAPER", url="https://b")],
        ),
        tmp_path,
    )
    digest = combined_digest(tmp_path)
    assert digest is not None
    assert digest.date == date(2026, 8, 2)

    # An explicit day still wins (used by tests and the live API).
    explicit = combined_digest(tmp_path, day=date(2026, 8, 5))
    assert explicit is not None
    assert explicit.date == date(2026, 8, 5)


def test_search_index_deduplicates_historical_stories():
    snapshots = [
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 1),
            stories=[Story(source="hn", external_id="1", title="Old", url="https://a")],
        ),
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 2),
            stories=[
                Story(
                    source="hn",
                    external_id="1",
                    title="New",
                    url="https://a",
                    snippet="Updated",
                )
            ],
        ),
    ]
    index = search_index(snapshots)
    assert len(index) == 1
    assert index[0]["title"] == "New"
    assert index[0]["snippet"] == "Updated"


def test_static_site_version_changes_when_artifact_changes(tmp_path):
    site = tmp_path / "site"
    static = site / "static"
    static.mkdir(parents=True)
    (static / "style.css").write_text("first")
    first = site_version(site)
    (static / "style.css").write_text("second")
    assert site_version(site) != first
    # Mutable files (fresh digest, feeds) never bump the SW cache version.
    (site / "index.html").write_text("digest one")
    (site / "feed.rss").write_text("<rss/>")
    assert site_version(site) == (site_version(site))


def test_registerspill_only_due_on_mondays(tmp_path):
    # 2026-08-03 is a Monday. Snapshot it so it's not a bootstrap fetch.
    save_snapshot(
        SourceSnapshot(source="registerspill", date=date(2026, 8, 3), stories=[]),
        tmp_path,
    )

    tuesday = date(2026, 8, 4)
    monday_next_week = date(2026, 8, 10)

    # Not enough elapsed time on Tuesday even though a fetch ran Monday.
    assert "registerspill" not in due_sources(tuesday, tmp_path)
    # A week later, on Monday, it becomes due again.
    assert "registerspill" in due_sources(monday_next_week, tmp_path)
    # But not on the intervening Tuesday.
    assert "registerspill" not in due_sources(date(2026, 8, 11), tmp_path)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from app import main as app_main

    monkeypatch.setattr(app_main, "DATA_DIR", tmp_path)
    with TestClient(app_main.app) as c:
        yield c


def test_api_empty_returns_404(client):
    assert client.get("/api/digest").status_code == 404
    assert client.get("/").status_code == 200


def test_api_pages_and_filters(client, tmp_path):
    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 2),
            stories=[Story(source="hn", title="HN story", url="https://a")],
        ),
        tmp_path,
    )
    save_snapshot(
        SourceSnapshot(
            source="arxiv",
            date=date(2026, 8, 2),
            stories=[Story(source="arxiv", title="arXiv paper", url="https://b")],
        ),
        tmp_path,
    )

    assert client.get("/").status_code == 200
    assert client.get("/archive/").status_code == 200
    archive = client.get("/archive/").text
    assert "Hacker News" in archive
    assert "Sunday" in archive
    assert "1 story" in archive
    assert client.get("/stats/").status_code == 200
    assert client.get("/sources/").status_code == 200
    assert client.get("/api/").status_code == 200
    assert client.get("/design/").status_code == 200
    assert client.get("/feed.rss").status_code == 200

    body = client.get("/api/stories", params={"source": "hn"}).json()
    assert [s["title"] for s in body] == ["HN story"]

    md = client.get("/api/stories.md").text
    assert "### 1. HN story" in md

    snap = client.get("/api/sources/hn").json()
    assert snap["source"] == "hn"
    assert client.get("/api/sources/hn.json").json() == snap
    assert client.get("/api/sources/nope").status_code == 404
    assert client.get("/api/sources/hn/2026-08-02").status_code == 200

    page = client.get("/archive/hn/2026-08-02/")
    assert page.status_code == 200
    assert "HN story" in page.text
    assert client.get("/archive/nope/2026-08-02/").status_code == 404


def test_sources_page_lists_sources(client, tmp_path):
    save_snapshot(
        SourceSnapshot(
            source="registerspill",
            date=date(2026, 8, 3),  # a Monday
            stories=[Story(source="registerspill", title="SP", url="https://x")],
        ),
        tmp_path,
    )
    page = client.get("/sources/")
    assert page.status_code == 200
    assert "Hacker News" in page.text
    assert "daily" in page.text
    assert "Register Spill" in page.text
    assert "weekly · Monday" in page.text


def test_source_registry_cadences(tmp_path):
    rows = {r["key"]: r for r in source_registry(tmp_path)}
    assert rows["hn"]["cadence"] == "daily"
    assert rows["arxiv"]["cadence"] == "weekly · Monday"
    assert rows["registerspill"]["cadence"] == "weekly · Monday"
    assert rows["hn"]["last_fetched"] is None


def test_fetch_status_reports_stale_sources(tmp_path):
    from app.config import SOURCES

    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 10),
            stories=[Story(source="hn", title="Older", url="https://a")],
        ),
        tmp_path,
    )
    statuses = {
        source: {"state": "skipped", "snapshot_date": None, "stories": 0}
        for source in SOURCES
    }
    statuses["hn"] = {
        "state": "stale",
        "snapshot_date": "2026-08-10",
        "stories": 1,
        "error": "temporary outage",
    }
    save_fetch_report(date(2026, 8, 11), tmp_path, statuses)

    report = fetch_status(tmp_path)
    assert report["date"] == date(2026, 8, 11)
    assert report["has_issues"] is True
    assert report["sources"]["hn"]["state_label"] == "Using older snapshot"
    assert report["sources"]["hn"]["snapshot_date"] == date(2026, 8, 10)
    assert report["sources"]["hn"]["detail"] == "temporary outage"


def test_build_site_copies_all_static_assets(tmp_path):
    # Regression: build_site only copied style.css + fonts, so favicon.svg 404'd
    # on the deployed site. The whole static dir must be copied.
    from pathlib import Path

    from scripts.build_site import build_site

    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 2),
            stories=[Story(source="hn", title="A", url="https://a")],
        ),
        tmp_path,
    )
    out = tmp_path / "site"
    out.mkdir()
    (out / "stale-page.html").write_text("old build")
    build_site(tmp_path, out, "/catnews", "https://example.com")

    app_static = Path(__file__).resolve().parent.parent / "app" / "static"
    for name in ("favicon.svg", "style.css"):
        assert (out / "static" / name).read_bytes() == (app_static / name).read_bytes()
    assert (out / "static" / "fonts").is_dir()
    assert (out / "static" / "favicon.svg").exists()
    assert not (out / "stale-page.html").exists()
    assert (out / "api" / "search.json").exists()
    assert (out / "api" / "fetch-status.json").exists()
    assert (out / "api" / "sources" / "hn.json").exists()

    from scripts.check_site import check_site

    assert check_site(out, "/catnews") == []


def test_config_loads_default_sources(tmp_path):
    from app.config import SOURCE_LABELS, SOURCE_TAGS, SOURCES

    assert "hn" in SOURCES
    assert "arxiv" in SOURCES
    assert "simonw" in SOURCES
    assert SOURCE_LABELS["github"] == "GitHub"
    assert SOURCE_TAGS["registerspill"] == "Register Spill"
    assert SOURCES["arxiv"]["weekday"] == 0


def test_config_loads_yaml_sources(tmp_path):
    from app.config import load_sources

    yaml_file = tmp_path / "sources.yaml"
    yaml_file.write_text(
        """
defaults:
  cadence_days: 1
  limit: 5
sources:
  - key: blog
    label: My Blog
    tag: BLOG
    type: rss
    url: https://example.com/feed
    color: "#123456"
  - key: hn
    label: Hacker News
    tag: HN
    type: builtin
    limit: 30
"""
    )
    sources = load_sources(yaml_file)
    assert set(sources) == {"blog", "hn"}
    assert sources["blog"]["type"] == "rss"
    assert sources["blog"]["url"] == "https://example.com/feed"
    # defaults applied, per-source limit overrides
    assert sources["blog"]["cadence_days"] == 1
    assert sources["blog"]["limit"] == 5
    assert sources["hn"]["limit"] == 30


def test_config_falls_back_to_builtin_when_yaml_missing(tmp_path):
    from app.config import load_sources

    missing = tmp_path / "nope.yaml"
    assert not missing.exists()
    sources = load_sources(missing)
    assert set(sources) == {"hn", "arxiv", "github", "registerspill", "simonw"}


def test_badge_css_covers_every_source():
    from app.config import SOURCES, badge_css

    css = badge_css()
    for key in SOURCES:
        assert f".badge-{key} {{" in css
        assert f"--badge-{key}:" in css
    assert '[data-theme="dark"]' in css
    assert '[data-theme="pitch"]' in css


def test_theme_cycle_includes_pitch_black():
    from app.config import badge_css

    css = badge_css()
    assert '[data-theme="dark"], [data-theme="pitch"]' in css


def test_css_defines_pitch_black_palette():
    css = (
        Path(__file__).resolve().parent.parent / "app" / "static" / "style.css"
    ).read_text()
    assert '[data-theme="pitch"]' in css
    assert "--paper: #0d0c0a;" in css


def test_base_theme_toggle_cycles_through_all_states():
    base = (
        Path(__file__).resolve().parent.parent / "app" / "templates" / "base.html"
    ).read_text()
    assert '["light", "dark", "pitch", "auto"]' in base
    assert "theme-color-meta" in base
    assert "catnewsChromeMeta" in base


def test_css_defines_radius_tokens():
    css = (
        Path(__file__).resolve().parent.parent / "app" / "static" / "style.css"
    ).read_text()
    assert "--radius-sm:" in css
    assert "--radius-pill:" in css
    assert css.count("var(--radius-sm)") > 10
    assert css.count("var(--radius-pill)") > 5
    assert "border-radius: 2px;" not in css


def test_base_has_theme_picker_menu():
    base = (
        Path(__file__).resolve().parent.parent / "app" / "templates" / "base.html"
    ).read_text()
    assert 'id="theme-menu"' in base
    assert 'data-theme-option="pitch"' in base
    assert "catnewsSetTheme" in base


def test_desktop_nav_is_inline():
    css = (
        Path(__file__).resolve().parent.parent / "app" / "static" / "style.css"
    ).read_text()
    assert ".js .menu-trigger { display: none; }" in css
    assert "@media (min-width: 861px)" in css


def test_story_cards_use_content_visibility():
    css = (
        Path(__file__).resolve().parent.parent / "app" / "static" / "style.css"
    ).read_text()
    assert "content-visibility: auto;" in css


def test_print_stylesheet_exists():
    css = (
        Path(__file__).resolve().parent.parent / "app" / "static" / "style.css"
    ).read_text()
    assert "@media print" in css
    assert ".story-title a::after" in css


def test_view_transitions_respect_reduced_motion():
    css = (
        Path(__file__).resolve().parent.parent / "app" / "static" / "style.css"
    ).read_text()
    assert "@view-transition { navigation: auto; }" in css
    assert "@view-transition { navigation: none; }" in css


def test_font_face_declares_full_variable_ranges():
    css = (
        Path(__file__).resolve().parent.parent / "app" / "static" / "style.css"
    ).read_text()
    assert css.count("font-weight: 200 900;") == 2
    assert "font-weight: 100 900;" in css


def test_skip_link_is_first_focusable_element():
    base = (
        Path(__file__).resolve().parent.parent / "app" / "templates" / "base.html"
    ).read_text()
    assert base.index('class="skip-link"') < base.index("<header")
    assert base.index('class="skip-link"') < base.index("site-header")


def test_manifest_registers_maskable_icon_and_shortcuts():
    import json

    from app.render import render_manifest

    manifest = json.loads(render_manifest())
    purposes = {icon["purpose"] for icon in manifest["icons"]}
    assert "any" in purposes
    assert "maskable" in purposes
    shortcut_names = {shortcut["name"] for shortcut in manifest["shortcuts"]}
    assert {"Archive", "Sources", "Stats"} <= shortcut_names


def test_help_dialog_documents_edition_nav():
    base = (
        Path(__file__).resolve().parent.parent / "app" / "templates" / "base.html"
    ).read_text()
    assert "Previous / next edition" in base


def test_favicon_matches_departure_ink_palette():
    svg = (
        Path(__file__).resolve().parent.parent / "app" / "static" / "favicon.svg"
    ).read_text()
    assert "#353431" in svg
    assert "#f0eee8" in svg
    assert "#1B365D" not in svg
    assert "#9db9db" not in svg


def test_sources_page_links_to_source_site():
    template = (
        Path(__file__).resolve().parent.parent / "app" / "templates" / "sources.html"
    ).read_text()
    assert 'href="{{ src.url }}"' in template
    registry_src = (
        Path(__file__).resolve().parent.parent / "app" / "store.py"
    ).read_text()
    assert '"url": cfg.get("url")' in registry_src


def test_feeds_carry_xslt_stylesheet():
    from app.render import FEED_STYLESHEET_PI, _with_feed_stylesheet

    assert "feed.xsl" in FEED_STYLESHEET_PI
    xml = "<?xml version='1.0' encoding='UTF-8'?>\n<rss></rss>"
    out = _with_feed_stylesheet(xml)
    assert out.index("xml-stylesheet") > out.index("<?xml")
    xsl = (
        Path(__file__).resolve().parent.parent / "app" / "static" / "feed.xsl"
    ).read_text()
    assert "xsl:stylesheet" in xsl


def test_print_opens_collapsed_details():
    js = (
        Path(__file__).resolve().parent.parent / "app" / "static" / "app.js"
    ).read_text()
    assert "beforeprint" in js
    assert "afterprint" in js


def test_get_fetcher_rss_and_api():
    from app.fetchers import get_fetcher

    rss_fn = get_fetcher({"key": "blog", "type": "rss", "url": "https://x/feed"})
    assert callable(rss_fn)
    hn_fn = get_fetcher({"key": "hn", "type": "builtin"})
    assert callable(hn_fn)

    with pytest.raises(KeyError):
        get_fetcher({"key": "bogus", "type": "builtin"})


def test_build_site_emits_pwa_files(tmp_path):
    # PWA: the static build must ship a manifest + service worker that precache
    # the stable app shell, so the cache name survives the daily data refresh
    # (mutable digest/feed/API files revalidate on demand instead).
    from scripts.build_site import build_site

    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 2),
            stories=[Story(source="hn", title="A", url="https://a")],
        ),
        tmp_path,
    )
    out = tmp_path / "site"
    build_site(tmp_path, out, "/catnews", "https://example.com")

    manifest = (out / "manifest.json").read_text()
    import json

    data = json.loads(manifest)
    assert data["name"].startswith("catnews")
    assert data["start_url"] == "./"
    assert data["display"] == "standalone"

    sw = (out / "sw.js").read_text()
    assert "PRECACHE" in sw
    import re

    match = re.search(r"PRECACHE = \[(.*?)\];", sw, re.DOTALL)
    assert match
    precache = match.group(1)
    # stable app shell + tiny health data is precached; the growing
    # search index is lazy-fetched on first search instead
    for rel in ('"./"', '"./static/style.css"', '"./404.html"', '"./archive/"'):
        assert rel in precache, f"missing {rel} in precache"
    assert '"./api/fetch-status.json"' in precache
    # mutable digest/feed/other API data is NOT precached (cache-name stability)
    for rel in (
        '"./index.html"',
        '"./feed.rss"',
        '"./api/stories.json"',
        '"./api/search.json"',
        '"./archive/hn/2026-08-02/"',
    ):
        assert rel not in precache, f"did not expect {rel} in precache"


def test_deploy_workflow_shares_pages_env_with_validation():
    from pathlib import Path

    import yaml

    workflow = yaml.safe_load(
        (
            Path(__file__).resolve().parent.parent
            / ".github"
            / "workflows"
            / "deploy.yml"
        ).read_text()
    )
    deploy = workflow["jobs"]["deploy"]
    assert deploy["env"]["BASE_PATH"] == "/${{ github.event.repository.name }}"
    assert deploy["env"]["BASE_URL"] == (
        "https://${{ github.event.repository.owner.login }}.github.io/"
        "${{ github.event.repository.name }}"
    )
    build = next(
        step for step in deploy["steps"] if step.get("name") == "Build static site"
    )
    validate = next(
        step for step in deploy["steps"] if step.get("name") == "Validate static site"
    )
    assert "env" not in build
    assert "env" not in validate
    assert '"$BASE_PATH"' in build["run"]
    assert '"$BASE_PATH"' in validate["run"]
    assert workflow["permissions"] == {}
    assert workflow["jobs"]["archive"]["permissions"] == {
        "contents": "write",
        "pull-requests": "write",
    }
    assert workflow["jobs"]["lint"]["permissions"] == {"contents": "read"}
    assert workflow["jobs"]["deploy"]["permissions"] == {
        "contents": "read",
        "pages": "write",
        "id-token": "write",
    }


def test_index_page_has_app_js_and_search(client, tmp_path):
    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 2),
            stories=[Story(source="hn", title="HN story", url="https://a")],
        ),
        tmp_path,
    )
    page = client.get("/").text
    # shared client script + PWA wiring present on every page
    assert 'src="/static/app.js?v=' in page
    assert 'rel="manifest"' in page
    assert 'register("/sw.js")' in page
    # search box is in the header
    assert 'id="search-input"' in page
    # story cards carry the URL needed by save/read/search
    assert 'data-url="https://a"' in page
    # filter affordances for the new reading model
    assert 'data-saved="saved"' in page
    assert 'id="hide-read"' in page
    # load-more for the growing feed
    assert 'id="load-more"' in page


def test_per_story_timestamp_rendered(client, tmp_path):
    # Each story card shows its published date so a daily digest is scannable.
    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 2),
            stories=[
                Story(
                    source="hn",
                    title="Timed story",
                    url="https://a",
                    published=datetime(2026, 8, 1, 9, 30, tzinfo=UTC),
                ),
                Story(source="hn", title="No date", url="https://b"),
            ],
        ),
        tmp_path,
    )
    page = client.get("/").text
    assert '<time datetime="2026-08-01T09:30:00+00:00">Aug 01, 2026</time>' in page
    assert "Aug 01, 2026" in page


def test_story_previews_are_not_rendered_on_cards(client, tmp_path):
    save_snapshot(
        SourceSnapshot(
            source="arxiv",
            date=date(2026, 8, 10),
            stories=[
                Story(
                    source="arxiv",
                    title="CoinRAG: Contextualized Information Nugget KV Cache Reuse",
                    url="https://arxiv.org/abs/2608.07458",
                    snippet="Recent optimization studies on Retrieval-Augmented Generation (RAG) have exploited chunk-level KV cache reuse.",
                )
            ],
        ),
        tmp_path,
    )
    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 10),
            stories=[
                Story(
                    source="hn",
                    title="Upvoted story",
                    url="https://news.example/1",
                    score=482,
                ),
                Story(
                    source="github",
                    title="Stared repo",
                    url="https://github.com/a/b",
                    score=999,
                ),
            ],
        ),
        tmp_path,
    )
    save_snapshot(
        SourceSnapshot(
            source="registerspill",
            date=date(2026, 8, 10),
            stories=[
                Story(
                    source="registerspill",
                    title="Joy & Curiosity #94",
                    url="https://registerspill.thorstenball.com/p/joy-and-curiosity-94",
                    links=[
                        CuratedLink(
                            title="What I Want to Tell You About Orbs",
                            url="https://ampcode.com/notes/what-i-want-to-tell-you-about-orbs",
                            site="ampcode.com",
                        ),
                    ],
                )
            ],
        ),
        tmp_path,
    )
    page = client.get("/").text
    assert "CoinRAG: Contextualized Information Nugget KV Cache Reuse" in page
    assert "Recent optimization studies on Retrieval-Augmented Generation" not in page
    assert "story-excerpt" not in page
    assert "story-more" not in page
    # curated links render on Register Spill cards
    assert "story-links" in page
    assert "1 curated link" in page
    assert "What I Want to Tell You About Orbs" in page
    # scores ARE rendered for sources that carry them (HN points, GitHub stars)
    assert '<span class="story-score">▲ 482</span>' in page
    assert '<span class="story-score">★ 999</span>' in page


def test_live_app_serves_pwa(client, tmp_path):
    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 2),
            stories=[Story(source="hn", title="A", url="https://a")],
        ),
        tmp_path,
    )
    manifest = client.get("/manifest.json")
    assert manifest.status_code == 200
    assert manifest.headers["content-type"] == "application/manifest+json"
    assert manifest.json()["short_name"] == "catnews"
    assert client.get("/static/style.css").status_code == 200
    assert client.get("/api/search.json").status_code == 200
    assert client.get("/api/fetch-status.json").status_code == 200

    sw = client.get("/sw.js")
    assert sw.status_code == 200
    assert sw.headers["content-type"] == "application/javascript"
    assert "PRECACHE" in sw.text
    assert '"./static/"' not in sw.text
    assert '"./archive/hn/2026-08-02/"' in sw.text

    assert "./static/" not in live_site_urls(
        [SourceSnapshot(source="hn", date=date(2026, 8, 2), stories=[])]
    )
    assert "./api/search.json" not in live_site_urls(
        [SourceSnapshot(source="hn", date=date(2026, 8, 2), stories=[])]
    )
    assert "./api/fetch-status.json" in live_site_urls(
        [SourceSnapshot(source="hn", date=date(2026, 8, 2), stories=[])]
    )


def test_service_worker_serves_api_data_network_first(client, tmp_path):
    # Regression: cached search.json used to be served stale-first, so the
    # first search after a fresh digest published returned yesterday's results.
    # API reads must behave like navigations: fresh when online, cached offline.
    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 2),
            stories=[Story(source="hn", title="A", url="https://a")],
        ),
        tmp_path,
    )
    sw = client.get("/sw.js").text
    # Navigations, API data, and the manifest are all network-first (fresh
    # when online); only stable shell assets are cache-first.
    assert 'request.mode === "navigate"' in sw
    assert 'url.pathname.indexOf("/api/") !== -1' in sw
    assert 'url.pathname.indexOf("/manifest.json") !== -1' in sw


def test_api_json_aliases_match_static_build(client, tmp_path):
    # The client-side search fetches /api/search.json; the live app must
    # expose the same .json endpoints the static build emits.
    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 2),
            stories=[Story(source="hn", title="Searchable story", url="https://a")],
        ),
        tmp_path,
    )
    for path in (
        "/api/stories.json",
        "/api/search.json",
        "/api/fetch-status.json",
        "/api/digest.json",
        "/api/stats.json",
        "/api/sources.json",
        "/api/sources/hn.json",
    ):
        assert client.get(path).status_code == 200, path
    stories = client.get("/api/stories.json").json()
    assert [s["title"] for s in stories] == ["Searchable story"]
    search = client.get("/api/search.json").json()
    assert [s["title"] for s in search] == ["Searchable story"]


def test_seo_meta_tags_on_pages(client, tmp_path):
    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 2),
            stories=[Story(source="hn", title="HN story", url="https://a")],
        ),
        tmp_path,
    )
    page = client.get("/").text
    # Open Graph
    assert 'property="og:site_name" content="catnews"' in page
    assert 'property="og:locale" content="en_US"' in page
    assert 'property="og:type" content="website"' in page
    assert 'property="og:title"' in page
    assert 'property="og:url"' in page
    assert 'property="og:image"' in page
    assert 'property="og:image:width" content="1200"' in page
    assert 'property="og:image:height" content="630"' in page
    # Twitter card
    assert 'name="twitter:card" content="summary_large_image"' in page
    assert 'name="twitter:title"' in page
    assert 'name="twitter:image"' in page
    # Meta description follows the page's og:description (per-page, not generic)
    assert 'property="og:description"' in page
    assert '<meta name="description" content="' in page
    # RSS autodiscovery link
    assert 'rel="alternate" type="application/rss+xml"' in page
    assert 'href="http://localhost:8000/feed.rss"' in page
    # iOS home-screen install support (matches the install dialog's iOS steps)
    assert '<link rel="apple-touch-icon"' in page
    assert '<meta name="mobile-web-app-capable" content="yes">' in page
    assert '<meta name="apple-mobile-web-app-capable" content="yes">' in page
    assert '<meta name="apple-mobile-web-app-title" content="catnews">' in page


def test_home_title_includes_edition_date(client, tmp_path):
    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 2),
            stories=[Story(source="hn", title="HN story", url="https://a")],
        ),
        tmp_path,
    )
    page = client.get("/").text
    assert "<title>catnews — August 02, 2026</title>" in page


def test_snapshot_title_and_description_include_date(client, tmp_path):
    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 2),
            stories=[Story(source="hn", title="HN story", url="https://a")],
        ),
        tmp_path,
    )
    page = client.get("/archive/hn/2026-08-02/").text
    assert "<title>catnews | Hacker News · August 02, 2026</title>" in page
    assert "hand-curated stories from Hacker News on August 02, 2026" in page


def test_story_cards_have_stable_deep_link_anchors(client, tmp_path):
    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 2),
            stories=[Story(source="hn", title="Anchored story", url="https://a/thing")],
        ),
        tmp_path,
    )
    home = client.get("/").text
    snapshot = client.get("/archive/hn/2026-08-02/").text
    import re as _re

    home_ids = _re.findall(r'id="(story-[0-9a-f]{10})"', home)
    assert len(home_ids) == 1
    snap_ids = _re.findall(r'id="(story-[0-9a-f]{10})"', snapshot)
    assert home_ids == snap_ids
    assert 'class="story"' in home
    app_js = client.get("/static/app.js").text
    assert "copy-toggle" in app_js
    # Regression: deep links must reveal the whole edition, not just the first
    # PAGE_SIZE stories, or links to cards past the load-more cutoff do nothing.
    assert "state.loaded = cards.length" in app_js
    # Regression: the SearchAction structured data advertises #q=… links; the
    # client must honor them or the advertised search deep link does nothing.
    assert "function runSearchHash()" in app_js
    assert "decodeURIComponent" in app_js


def test_weekly_trends_buckets_by_iso_week(tmp_path):
    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 3),
            stories=[
                Story(source="hn", title="HN1", url="https://a"),
                Story(source="hn", title="HN2", url="https://b"),
            ],
        ),
        tmp_path,
    )
    save_snapshot(
        SourceSnapshot(
            source="github",
            date=date(2026, 8, 4),
            stories=[Story(source="github", title="Repo", url="https://c")],
        ),
        tmp_path,
    )
    save_snapshot(
        SourceSnapshot(
            source="arxiv",
            date=date(2026, 8, 10),
            stories=[Story(source="arxiv", title="Paper", url="https://d")],
        ),
        tmp_path,
    )

    trends = weekly_trends(tmp_path)
    assert [r["week"] for r in trends] == ["2026-W32", "2026-W33"]
    assert trends[0]["counts"] == {"github": 1, "hn": 2}
    assert trends[0]["total"] == 3
    assert trends[1]["counts"] == {"arxiv": 1}
    assert trends[1]["start"] == date(2026, 8, 10)


def test_daily_counts_zero_fills_gaps(tmp_path):
    from app.store import daily_counts

    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 10),
            stories=[
                Story(source="hn", title="A", url="https://a"),
                Story(source="hn", title="B", url="https://b"),
            ],
        ),
        tmp_path,
    )
    save_snapshot(
        SourceSnapshot(
            source="arxiv",
            date=date(2026, 8, 12),
            stories=[Story(source="arxiv", title="P", url="https://arxiv.org/abs/1")],
        ),
        tmp_path,
    )
    daily = daily_counts(tmp_path)
    assert len(daily) == 3  # 8/10, 8/11, 8/12
    assert daily[0] == {"date": date(2026, 8, 10), "count": 2}
    assert daily[1] == {"date": date(2026, 8, 11), "count": 0}
    assert daily[2] == {"date": date(2026, 8, 12), "count": 1}


def test_render_heatmap_svg_auto_fits_window(monkeypatch):
    from app.render import render_heatmap_svg

    monkeypatch.setattr("app.render.today_utc", lambda: date(2026, 8, 14))
    daily = [
        {"date": date(2026, 8, 10), "count": 2},
        {"date": date(2026, 8, 11), "count": 0},
        {"date": date(2026, 8, 12), "count": 1},
    ]
    svg = render_heatmap_svg(daily)
    assert 'class="trend-chart heatmap"' in svg
    # Auto-fit starts at the Monday of the first data week and only spans the
    # active period, not a fixed six-month window (which would be ~26 columns).
    monday = re.search(r'data-date="(2026-\d\d-\d\d)"', svg)
    assert monday is not None
    assert (
        monday.group(1) <= "2026-08-10"
    )  # first column begins at/before first data day
    assert "2026-08-10" in svg
    assert "2026-08-12" in svg
    assert len(re.findall(r"<rect ", svg)) < 14  # a few weeks, not six months


def test_render_heatmap_svg_draws_year_boundary_hairline():
    from app.render import render_heatmap_svg

    daily = [
        {"date": date(2025, 12, 29), "count": 1},
        {"date": date(2026, 1, 5), "count": 2},
    ]
    svg = render_heatmap_svg(daily)
    assert '<line class="heatmap-year"' in svg


def test_sparkline_points_normalizes_weekly_counts():
    from app.render import sparkline_points

    weekly = [
        {"counts": {"hn": 10, "blog": 0}, "total": 10},
        {"counts": {"hn": 20, "blog": 5}, "total": 25},
        {"counts": {"hn": 5, "blog": 8}, "total": 13},
    ]
    points = sparkline_points(weekly, "hn")
    assert points is not None
    n = len(points["points"].split())
    assert n == 3  # one point per week
    # Peak week maps to the top of the chart, empty-to-zero weeks to baseline.
    tokens = [tuple(map(float, p.split(","))) for p in points["points"].split(" ")]
    assert tokens[1][1] < tokens[0][1]
    xs = [t[0] for t in tokens]
    assert xs == sorted(xs)
    # Area closes the line onto the baseline; end dot rides the last point.
    assert points["area"].endswith("97.0,25.0 3.0,25.0")
    assert points["last"]["x"] == "97.0"
    assert points["last"]["y"] == f"{tokens[2][1]:.1f}"

    # A source missing from every week renders a flat baseline sparkline.
    flat = sparkline_points(weekly, "missing")
    assert flat is not None
    ys = {p.split(",")[1] for p in flat["points"].split(" ")}
    assert len(ys) == 1

    # Fewer than two weeks of data yields no sparkline.
    assert sparkline_points([weekly[0]], "hn") is None


def test_help_dialog_and_shortcut_markup():
    base = (
        Path(__file__).resolve().parent.parent / "app" / "templates" / "base.html"
    ).read_text()
    assert 'id="help-dialog"' in base
    assert 'id="help-toggle"' in base
    assert "footer-personal" in base
    assert "footer-to-top" in base
    assert "scroll-progress" in base


def test_top_domains_and_arxiv_categories(tmp_path):
    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 3),
            stories=[
                Story(source="hn", title="A", url="https://www.bbc.com/news/a"),
                Story(source="hn", title="B", url="https://bbc.com/news/b"),
                Story(source="hn", title="C", url="https://openai.com/blog"),
            ],
        ),
        tmp_path,
    )
    save_snapshot(
        SourceSnapshot(
            source="arxiv",
            date=date(2026, 8, 3),
            stories=[
                Story(
                    source="arxiv", title="P1", url="https://a.com/1", category="cs.LG"
                ),
                Story(
                    source="arxiv", title="P2", url="https://b.com/2", category="cs.LG"
                ),
                Story(
                    source="arxiv", title="P3", url="https://c.com/3", category="cs.AI"
                ),
            ],
        ),
        tmp_path,
    )

    domains = top_domains(tmp_path)
    assert domains[0] == ("bbc.com", 2)
    assert ("openai.com", 1) in domains
    assert arxiv_category_counts(tmp_path) == [("cs.LG", 2), ("cs.AI", 1)]
    assert days_archiving(tmp_path) == 1


def test_fetch_health_compares_actual_to_expected(tmp_path):
    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 3),
            stories=[Story(source="hn", title="A", url="https://a")],
        ),
        tmp_path,
    )
    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 4),
            stories=[Story(source="hn", title="B", url="https://b")],
        ),
        tmp_path,
    )

    health = fetch_health(tmp_path)
    by_source = {row["source"]: row for row in health}
    assert "hn" in by_source
    assert by_source["hn"]["actual"] == 2
    assert by_source["hn"]["expected"] >= 2
    assert by_source["hn"]["rate"] == 100.0
    assert by_source["hn"]["last_fetched"] == date(2026, 8, 4)
    assert all(
        row["source"] in {"hn", "arxiv", "github", "registerspill", "simonw"}
        for row in health
    )


def test_stats_page_and_trends_endpoint(client, tmp_path):
    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 3),
            stories=[Story(source="hn", title="HN story", url="https://a")],
        ),
        tmp_path,
    )
    save_snapshot(
        SourceSnapshot(
            source="arxiv",
            date=date(2026, 8, 10),
            stories=[
                Story(
                    source="arxiv",
                    title="Paper",
                    url="https://arxiv.org/abs/2607.1",
                    category="cs.LG",
                )
            ],
        ),
        tmp_path,
    )

    page = client.get("/stats/").text
    assert "Stories per day" in page
    assert 'class="trend-chart heatmap"' in page
    assert 'class="heat heat-' in page
    assert "View weekly data table" in page
    assert "Top domains" in page
    assert "arxiv.org" in page
    assert "arXiv categories" in page
    assert "cs.LG" in page
    assert "Fetch health" in page
    assert "Days archiving" in page
    assert "stat-table--trends" in page

    trends = client.get("/api/trends.json").json()
    assert [r["week"] for r in trends] == ["2026-W32", "2026-W33"]
    assert trends[0]["counts"]["hn"] == 1

    page = client.get("/").text
    assert 'id="export-saved"' in page


def test_safe_http_url_guards_schemes():
    from app.fetchers.sanitize import safe_http_url

    assert safe_http_url("https://example.com/a") == "https://example.com/a"
    assert safe_http_url("http://example.com") == "http://example.com"
    assert safe_http_url("javascript:alert(1)") is None
    assert safe_http_url("data:text/html,x") is None
    assert safe_http_url("ftp://example.com") is None
    assert safe_http_url("/relative/path") is None
    assert safe_http_url(None, fallback="fb") == "fb"
    assert safe_http_url("javascript:alert(1)", fallback="fb") == "fb"


def test_safe_http_url_upgrades_https_only_hosts():
    from app.fetchers.sanitize import safe_http_url

    assert (
        safe_http_url("http://arxiv.org/abs/2607.28628v1")
        == "https://arxiv.org/abs/2607.28628v1"
    )
    assert (
        safe_http_url("http://www.arxiv.org/abs/2607.28628v1")
        == "https://www.arxiv.org/abs/2607.28628v1"
    )
    assert safe_http_url("https://arxiv.org/abs/x") == "https://arxiv.org/abs/x"
    # Subdomains other than www keep their scheme (only known-good hosts upgrade).
    assert safe_http_url("http://export.arxiv.org/api/query") == (
        "http://export.arxiv.org/api/query"
    )
    # Unrelated http URLs are untouched.
    assert safe_http_url("http://example.com/a") == "http://example.com/a"


def test_hn_unsafe_url_falls_back_to_item():
    hit = dict(SAMPLE_HIT)
    hit["url"] = "javascript:alert(1)"
    story = parse_hit(hit)
    assert story.url == "https://news.ycombinator.com/item?id=49138188"


def test_rss_drops_non_http_link():
    entry = {"title": "Sneaky", "link": "javascript:alert(1)"}
    assert parse_rss_entry(entry, "escflat") is None


def test_rss_links_drop_non_http():
    body = (
        '<a href="javascript:alert(1)">badcode</a>'
        '<a href="mailto:a@b.c">mailme</a>'
        '<a href="https://ok.example/thing">good enough</a>'
    )
    urls = [link.url for link in parse_links(body)]
    assert urls == ["https://ok.example/thing"]


def test_walk_site_urls_precaches_only_stable_files(tmp_path):
    from app.render import walk_site_urls

    (tmp_path / "static").mkdir()
    (tmp_path / "static" / "style.css").write_text("a{}")
    (tmp_path / "index.html").write_text("<h1>x</h1>")
    (tmp_path / "feed.rss").write_text("<rss/>")
    (tmp_path / "sitemap.xml").write_text("<urlset/>")
    (tmp_path / "404.html").write_text("<h1>nf</h1>")
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "stories.json").write_text("[]")
    (tmp_path / "api" / "search.json").write_text("[]")
    (tmp_path / "api" / "fetch-status.json").write_text("{}")
    (tmp_path / "archive" / "hn" / "2026-08-02").mkdir(parents=True)
    (tmp_path / "archive" / "hn" / "2026-08-02" / "index.html").write_text(
        "<h1>snap</h1>"
    )

    urls = walk_site_urls(tmp_path)
    assert "./static/style.css" in urls
    assert "./404.html" in urls
    assert "./index.html" not in urls
    assert "./feed.rss" not in urls
    assert "./sitemap.xml" not in urls
    assert "./api/stories.json" not in urls
    assert "./api/search.json" not in urls
    assert "./api/fetch-status.json" in urls
    assert "./archive/hn/2026-08-02/" not in urls


def test_site_version_ignores_mutable_files(tmp_path):
    (tmp_path / "static").mkdir()
    (tmp_path / "static" / "app.js").write_text("x")
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "stories.json").write_text("old")
    (tmp_path / "index.html").write_text("old")

    v1 = site_version(tmp_path)
    (tmp_path / "api" / "stories.json").write_text("new")
    (tmp_path / "index.html").write_text("new")
    (tmp_path / "feed.rss").write_text("<rss/>")
    assert site_version(tmp_path) == v1

    (tmp_path / "static" / "app.js").write_text("changed")
    assert site_version(tmp_path) != v1


def test_og_image_renders_valid_png():
    import struct

    from app.og_image import render_og_image

    png = render_og_image()
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    width, height = struct.unpack(">II", png[16:24])
    assert (width, height) == (1200, 630)


def test_404_page_served_and_home_has_social_meta(client, tmp_path):
    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 2),
            stories=[Story(source="hn", title="HN story", url="https://a")],
        ),
        tmp_path,
    )

    assert client.get("/404.html").status_code == 200
    assert "Not found" in client.get("/404.html").text

    home = client.get("/").text
    assert '<link rel="canonical"' in home
    assert "/static/og/home/2026-08-02.png" in home
    assert 'rel="noopener noreferrer"' in home


def test_repo_link_uses_config_repo_url(client, monkeypatch):
    from app import render

    home = client.get("/").text
    assert 'class="repo-link" href="https://github.com/mkmlman/catnews"' in home

    monkeypatch.setattr(render, "REPO_URL", "https://github.com/forker/forked")
    page = client.get("/").text
    assert 'class="repo-link" href="https://github.com/forker/forked"' in page
    assert "mkmlman/catnews" not in page


def test_stats_sparkline_has_role_img_not_aria_hidden(client, tmp_path):
    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 3),
            stories=[Story(source="hn", title="HN story", url="https://a")],
        ),
        tmp_path,
    )
    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 10),
            stories=[Story(source="hn", title="HN story 2", url="https://b")],
        ),
        tmp_path,
    )
    page = client.get("/stats/").text
    spark = 'class="stat-spark"'
    assert spark in page
    assert 'role="img" aria-label="Hacker News weekly story trend"' in page
    assert (
        'class="stat-spark" viewBox="0 0 100 28" preserveAspectRatio="none" aria-hidden="true"'
        not in page
    )


def test_api_page_gives_every_endpoint_copy_affordances(client, tmp_path):
    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 2),
            stories=[Story(source="hn", title="HN story", url="https://a")],
        ),
        tmp_path,
    )
    page = client.get("/api/").text
    # The per-source and per-date endpoints previously had no tools at all.
    assert 'data-run="/api/sources/hn.json"' in page
    assert 'data-copy="curl http://localhost:8000/api/sources/hn.json"' in page
    assert "api/sources/&lt;source&gt;/&lt;date&gt;" in page
    assert (
        'data-copy="curl http://localhost:8000/api/sources/&lt;source&gt;/&lt;date&gt;"'
        in page
    )
    # The description lists human tags, not internal keys.
    assert "— HN, arXiv, GitHub, Register Spill, simonw." in page


def test_story_cards_render_why_read_notes(client, tmp_path):
    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 2),
            stories=[
                Story(
                    source="hn",
                    title="HN story",
                    url="https://a",
                    why_read="Read this before your next one.",
                )
            ],
        ),
        tmp_path,
    )
    home = client.get("/").text
    assert (
        '<p class="story-why-read"><strong>Why read:</strong> Read this before your next one.</p>'
        in home
    )
    page = client.get("/archive/hn/2026-08-02/").text
    assert "Why read:" in page
    assert "Read this before your next one." in page


def test_json_ld_structured_data_on_pages(client, tmp_path):
    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 2),
            stories=[Story(source="hn", title="HN story", url="https://a")],
        ),
        tmp_path,
    )
    home = client.get("/").text
    assert '<script type="application/ld+json">' in home
    assert '"@type": "WebSite"' in home
    assert '"@type": "SearchAction"' in home
    assert '"@type": "ItemList"' in home
    assert '"name": "HN story"' in home
    # Escaping: a crafted title must not break out of the JSON-LD payload.
    save_snapshot(
        SourceSnapshot(
            source="arxiv",
            date=date(2026, 8, 2),
            stories=[
                Story(source="arxiv", title='A "quoted" <title>', url="https://b")
            ],
        ),
        tmp_path,
    )
    arxiv_page = client.get("/archive/arxiv/2026-08-02/").text
    assert '"@type": "BreadcrumbList"' in arxiv_page
    assert '"@type": "ItemList"' in arxiv_page
    archive = client.get("/archive/").text
    assert '"@type": "BreadcrumbList"' in archive


def test_index_has_filter_status_announce_region(client, tmp_path):
    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 2),
            stories=[Story(source="hn", title="HN story", url="https://a")],
        ),
        tmp_path,
    )
    page = client.get("/").text
    assert '<p class="sr-only" id="filter-status" aria-live="polite"></p>' in page


def test_sitemap_includes_lastmod(tmp_path):
    from scripts.build_site import build_site

    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 2),
            stories=[Story(source="hn", title="A", url="https://a")],
        ),
        tmp_path,
    )
    out = tmp_path / "site"
    build_site(tmp_path, out, "/catnews", "https://example.com")
    sitemap = (out / "sitemap.xml").read_text()
    assert sitemap.count("<lastmod>") == 7  # 6 shared pages + 1 snapshot
    assert "<lastmod>2026-08-02</lastmod>" in sitemap


def test_manifest_theme_color_matches_page_background():
    import json

    from app.render import render_manifest

    data = json.loads(render_manifest())
    assert data["theme_color"] == data["background_color"] == "#faf9f6"
    assert data["id"] == "./"
    assert data["display_override"] == ["standalone", "minimal-ui"]
    purposes = {icon.get("purpose") for icon in data["icons"]}
    assert purposes == {"any", "maskable"}


def test_design_page_stat_cards_use_real_data(client, tmp_path):
    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 2),
            stories=[
                Story(source="hn", title="A", url="https://a"),
                Story(source="hn", title="B", url="https://b"),
            ],
        ),
        tmp_path,
    )
    page = client.get("/design/").text
    assert 'stat-label">Stories curated</span>' in page
    assert '<span class="stat-value">2</span>' in page
    assert '<span class="stat-value">1</span>' in page


# --- Per-edition Open Graph cards -------------------------------------------


def test_og_image_caption_card_renders_valid_png():
    import struct

    from app.og_image import render_og_image

    plain = render_og_image()
    card = render_og_image(
        date_line="08.19.2026",
        count_line="25 STORIES",
        accent=(156, 77, 20),
    )
    for png in (plain, card):
        assert png.startswith(b"\x89PNG\r\n\x1a\n")
        width, height = struct.unpack(">II", png[16:24])
        assert (width, height) == (1200, 630)
    assert card != plain


def test_build_site_emits_per_edition_og_cards(tmp_path):
    from scripts.build_site import build_site

    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 2),
            stories=[Story(source="hn", title="A", url="https://a")],
        ),
        tmp_path,
    )
    out = tmp_path / "site2"
    build_site(tmp_path, out, "/catnews", "https://example.com")

    card = out / "static" / "og" / "hn" / "2026-08-02.png"
    assert card.is_file()
    assert card.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")

    snapshot_page = out / "archive" / "hn" / "2026-08-02" / "index.html"
    html = snapshot_page.read_text()
    assert "https://example.com/static/og/hn/2026-08-02.png" in html
    home = (out / "index.html").read_text()
    assert "https://example.com/static/og/home/2026-08-02.png" in home


def test_og_cards_stay_out_of_service_worker_precache(tmp_path):
    from scripts.build_site import build_site

    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 2),
            stories=[Story(source="hn", title="A", url="https://a")],
        ),
        tmp_path,
    )
    out = tmp_path / "site3"
    build_site(tmp_path, out, "/catnews", "https://example.com")

    sw = (out / "sw.js").read_text()
    assert "./static/og/" not in sw
    assert "./feed-hn.rss" not in sw

    # Per-edition cards are stable once written; they must not churn the cache
    # fingerprint that names the service worker cache.

    v1 = site_version(out)
    (out / "static" / "og" / "hn" / "2026-08-02.png").write_bytes(b"x")
    assert site_version(out) == v1


def test_live_app_serves_edition_cards_and_source_feeds(client, tmp_path):
    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 2),
            stories=[Story(source="hn", title="A", url="https://a")],
        ),
        tmp_path,
    )
    card = client.get("/static/og/hn/2026-08-02.png")
    assert card.status_code == 200
    assert card.headers["content-type"] == "image/png"
    assert card.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert client.get("/static/og/hn/2026-08-03.png").status_code == 404

    feed = client.get("/feed-hn.rss")
    assert feed.status_code == 200
    assert "application/rss" in feed.headers["content-type"]
    assert client.get("/feed-nope.rss").status_code == 404

    page = client.get("/archive/hn/2026-08-02/").text
    assert "http://localhost:8000/static/og/hn/2026-08-02.png" in page
    # Referenced by both og:image and twitter:image.
    assert page.count("/static/og/hn/2026-08-02.png") == 2


def test_sources_page_lists_feed_links(client, tmp_path):
    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 2),
            stories=[Story(source="hn", title="A", url="https://a")],
        ),
        tmp_path,
    )
    page = client.get("/sources/").text
    assert 'href="/feed-hn.rss"' in page


# --- Per-source RSS feeds ----------------------------------------------------


def test_build_site_emits_per_source_feeds(tmp_path):
    import xml.etree.ElementTree as ET

    from scripts.build_site import build_site

    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 2),
            stories=[
                Story(source="hn", title="A", url="https://a"),
                Story(source="hn", title="B", url="https://b"),
            ],
        ),
        tmp_path,
    )
    save_snapshot(
        SourceSnapshot(
            source="arxiv",
            date=date(2026, 8, 9),
            stories=[Story(source="arxiv", title="Paper", url="https://p")],
        ),
        tmp_path,
    )
    out = tmp_path / "site4"
    build_site(tmp_path, out, "/catnews", "https://example.com")

    hn_feed = out / "feed-hn.rss"
    arxiv_feed = out / "feed-arxiv.rss"
    assert hn_feed.is_file() and arxiv_feed.is_file()
    ET.fromstring(hn_feed.read_bytes())
    ET.fromstring(arxiv_feed.read_bytes())
    # The feed carries its own stable id + a channel link to the snapshot page.
    text = hn_feed.read_text()
    assert "https://example.com/feed-hn.rss" in text
    assert "https://example.com/archive/hn/2026-08-02/" in text


# --- Link-rot checker --------------------------------------------------------


def test_collect_story_urls_dedupes_and_filters():
    from scripts.check_links import collect_story_urls

    stories = [
        {
            "source": "hn",
            "title": "A",
            "url": "https://example.com/x",
            "hn_url": "https://news.ycombinator.com/item?id=1",
            "links": [{"url": "https://example.com/x"}],
        },
        {
            "source": "github",
            "title": "B",
            "url": "mailto:a@b.com",  # ignored
        },
        {"source": "arxiv", "title": "C", "url": "https://arxiv.org/abs/1"},
    ]
    urls = [r["url"] for r in collect_story_urls(stories)]
    assert urls == [
        "https://example.com/x",
        "https://news.ycombinator.com/item?id=1",
        "https://arxiv.org/abs/1",
    ]


def test_classify_status():
    from scripts.check_links import classify_status

    assert classify_status(200) == "good"
    assert classify_status(304) == "good"
    assert classify_status(404) == "dead"
    assert classify_status(410) == "dead"
    assert classify_status(451) == "dead"
    # 4xx bot-blocks are "could not verify" (error), never a false "dead".
    assert classify_status(403) == "error"
    assert classify_status(429) == "error"
    assert classify_status(401) == "error"
    assert classify_status(503) == "error"
    assert classify_status(None) == "error"


def test_render_markdown_report_lists_dead_links():
    from scripts.check_links import render_markdown_report

    report = render_markdown_report(
        [
            {
                "url": "https://gone.example",
                "title": "Gone",
                "source": "hn",
                "state": "dead",
                "status": 404,
            },
            {
                "url": "https://ok.example",
                "title": "Ok",
                "source": "arxiv",
                "state": "good",
                "status": 200,
            },
            {
                "url": "https://maybe.example",
                "title": "Maybe",
                "source": "hn",
                "state": "error",
                "status": None,
                "error": "ConnectTimeout",
            },
        ]
    )
    assert "## Dead links (1)" in report
    assert "https://gone.example" in report
    assert "ConnectTimeout" in report
    assert "https://ok.example" not in report


# --- Home edition card -------------------------------------------------------


def test_home_edition_card_rendered_and_served(client, tmp_path):
    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 2),
            stories=[Story(source="hn", title="A", url="https://a")],
        ),
        tmp_path,
    )
    home = client.get("/").text
    assert "/static/og/home/2026-08-02.png" in home
    assert 'data-digest-date="2026-08-02"' in home

    card = client.get("/static/og/home/2026-08-02.png")
    assert card.status_code == 200
    assert card.headers["content-type"] == "image/png"
    assert card.content.startswith(b"\x89PNG\r\n\x1a\n")

    # A card for an edition that was never published must not be served.
    assert client.get("/static/og/home/2026-08-03.png").status_code == 404


def test_search_index_records_carry_edition_date():
    from app.render import search_index

    snapshots = [
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 2),
            stories=[Story(source="hn", url="https://a", title="A")],
        )
    ]
    record = search_index(snapshots)[0]
    assert record["date"] == "2026-08-02"


def test_search_index_includes_why_read():
    from app.render import search_index

    snapshots = [
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 2),
            stories=[
                Story(
                    source="hn",
                    url="https://a",
                    title="A",
                    why_read="A systematic approach to docs.",
                )
            ],
        )
    ]
    record = search_index(snapshots)[0]
    assert record["why_read"] == "A systematic approach to docs."


def test_build_site_emits_home_edition_card(tmp_path):
    from scripts.build_site import build_site

    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 2),
            stories=[Story(source="hn", title="A", url="https://a")],
        ),
        tmp_path,
    )
    out = tmp_path / "site_home"
    build_site(tmp_path, out, "/catnews", "https://example.com")

    card = out / "static" / "og" / "home" / "2026-08-02.png"
    assert card.is_file()
    assert card.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert (
        "https://example.com/static/og/home/2026-08-02.png"
        in (out / "index.html").read_text()
    )


# --- Dead-link badges (consumed from the weekly check_links.py report) -------


def test_load_dead_links_parses_report(tmp_path):
    import json

    from app.render import load_dead_links

    report = tmp_path / "linkcheck.json"
    report.write_text(
        json.dumps(
            {
                "generated": "2026-08-16T05:00:00Z",
                "summary": {"good": 1, "dead": 2, "error": 1},
                "results": [
                    {
                        "url": "https://gone-a",
                        "source": "hn",
                        "title": "Gone A",
                        "domain": "gone-a",
                        "status": 404,
                        "state": "dead",
                        "error": None,
                    },
                    {
                        "url": "https://gone-b",
                        "source": "arxiv",
                        "title": "Gone B",
                        "domain": "gone-b",
                        "status": 410,
                        "state": "dead",
                        "error": None,
                    },
                    {
                        "url": "https://blocked",
                        "source": "hn",
                        "title": "Bot-blocked",
                        "domain": "blocked",
                        "status": 403,
                        "state": "dead",
                        "error": None,
                    },
                    {
                        "url": "https://ok",
                        "source": "hn",
                        "title": "Ok",
                        "domain": "ok",
                        "status": 200,
                        "state": "good",
                        "error": None,
                    },
                    {
                        "url": "https://unverifiable",
                        "source": "hn",
                        "title": "Uh",
                        "domain": "unverifiable",
                        "status": None,
                        "state": "error",
                        "error": "ConnectTimeout",
                    },
                ],
            }
        )
    )
    dead = load_dead_links(report)
    assert set(dead) == {"https://gone-a", "https://gone-b"}
    assert dead["https://gone-a"]["status"] == 404
    assert "https://blocked" not in dead
    report.write_text("not json")
    assert load_dead_links(report) == {}


def test_build_site_stamps_dead_link_badges(tmp_path):
    import json

    from scripts.build_site import build_site

    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 2),
            stories=[
                Story(
                    source="hn",
                    title="Rotted story",
                    url="https://gone-story",
                    hn_url="https://gone-discussion",
                    links=[CuratedLink(title="Inner", url="https://gone-inner")],
                ),
                Story(source="hn", title="Still live", url="https://ok-story"),
            ],
        ),
        tmp_path,
    )
    (tmp_path / "linkcheck.json").write_text(
        json.dumps(
            {
                "results": [
                    {
                        "url": "https://gone-story",
                        "state": "dead",
                        "status": 404,
                        "title": "Rotted story",
                        "source": "hn",
                    },
                    {
                        "url": "https://gone-discussion",
                        "state": "dead",
                        "status": 404,
                        "title": "Rotted story",
                        "source": "hn",
                    },
                    {
                        "url": "https://gone-inner",
                        "state": "dead",
                        "status": 410,
                        "title": "Inner",
                        "source": "hn",
                    },
                ]
            }
        )
    )
    out = tmp_path / "site_badges"
    build_site(tmp_path, out, "/catnews", "https://example.com")

    home = (out / "index.html").read_text()
    assert home.count('class="story-dead">Dead link</span>') == 1
    assert 'href="https://gone-story"' in home and 'class="is-dead"' in home
    assert 'class="discuss is-dead" href="https://gone-discussion"' in home
    assert 'rel="noopener noreferrer" class="is-dead"' in home
    # Confirmed-gone links get a Wayback Machine rescue link.
    assert (
        'class="story-archived" href="https://web.archive.org/web/2/https://gone-story"'
        in home
    )
    assert (
        'class="story-archived-link" href="https://web.archive.org/web/2/https://gone-inner"'
        in home
    )
    dead_api = json.loads((out / "api" / "dead-links.json").read_text())
    assert {r["url"] for r in dead_api} == {
        "https://gone-story",
        "https://gone-discussion",
        "https://gone-inner",
    }

    ok_anchor = 'data-url="https://ok-story"'
    ok_card = home[home.index(ok_anchor) : home.index(ok_anchor) + 1600]
    assert "is-dead" not in ok_card and "Dead link" not in ok_card
    assert "web.archive.org" not in ok_card

    snap_page = (out / "archive" / "hn" / "2026-08-02" / "index.html").read_text()
    assert snap_page.count('class="story-dead">Dead link</span>') == 1


def test_dev_server_exposes_dead_links(client, tmp_path):
    import json

    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 2),
            stories=[
                Story(source="hn", title="Rotted", url="https://gone-story"),
                Story(source="hn", title="Live", url="https://ok-story"),
            ],
        ),
        tmp_path,
    )
    (tmp_path / "linkcheck.json").write_text(
        json.dumps(
            {
                "results": [
                    {
                        "url": "https://gone-story",
                        "state": "dead",
                        "status": 404,
                        "title": "Rotted",
                        "source": "hn",
                    }
                ]
            }
        )
    )
    home = client.get("/").text
    assert 'class="story-dead">Dead link</span>' in home
    dead = client.get("/api/dead-links.json")
    assert dead.status_code == 200
    assert dead.json() == [
        {
            "url": "https://gone-story",
            "state": "dead",
            "status": 404,
            "title": "Rotted",
            "source": "hn",
        }
    ]
    assert client.get("/api/dead-links").json() == dead.json()


def test_light_theme_text_tokens_meet_contrast():
    import re
    from pathlib import Path

    css_path = Path(__file__).resolve().parent.parent / "app" / "static" / "style.css"
    css = css_path.read_text()
    match = re.search(r":root\s*\{([^}]*)\}", css, re.DOTALL)
    assert match is not None
    root = match.group(1)
    tokens = dict(re.findall(r"(--[\w-]+):\s*(#[0-9a-fA-F]{6})\s*;", root))
    paper, card = tokens["--paper"], tokens["--card"]
    muted, faint = tokens["--muted"], tokens["--faint"]

    def lum(hex_color: str) -> float:
        def f(c: float) -> float:
            return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

        hex_color = hex_color.lstrip("#")
        r, g, b = [int(hex_color[i : i + 2], 16) / 255 for i in (0, 2, 4)]
        r, g, b = map(f, (r, g, b))
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    def contrast(a: str, b: str) -> float:
        l1, l2 = sorted((lum(a), lum(b)), reverse=True)
        return (l1 + 0.05) / (l2 + 0.05)

    assert contrast(muted, paper) >= 4.5
    assert contrast(muted, card) >= 4.5
    assert contrast(faint, paper) >= 3.0


# --- Regression tests from the review round (digest size, corruption, ghosts)


def test_latest_stories_backfills_rolling_sources_to_limit(tmp_path):
    from app.store import latest_stories

    # A rolling source archives only *new* stories (deltas), so snapshots are
    # small (2/day) even though the source limit is 15. latest_stories merges
    # across editions so the digest again shows the full top-N.
    save_snapshot(
        SourceSnapshot(
            source="github",
            date=date(2026, 8, 1),
            stories=[
                Story(source="github", title="Curated", url="https://g/1", score=10),
            ],
        ),
        tmp_path,
    )
    save_snapshot(
        SourceSnapshot(
            source="github",
            date=date(2026, 8, 2),
            stories=[
                Story(source="github", title="Next", url="https://g/2", score=9),
                Story(
                    source="github", title="Curated again", url="https://g/1", score=12
                ),
            ],
        ),
        tmp_path,
    )
    merged = latest_stories("github", tmp_path)
    assert [s.title for s in merged] == ["Next", "Curated again"]

    limited = latest_stories("github", tmp_path, limit=1)
    assert [s.title for s in limited] == ["Next"]

    digest = combined_digest(tmp_path)
    assert digest is not None
    assert [s.title for s in digest.stories] == ["Next", "Curated again"]


def test_combined_digest_includes_backfilled_stories(tmp_path):
    # GitHub's trending snapshot for Aug 3 only archived one new story, but the
    # digest must still show the full configured per-source top-N by merging
    # the previous snapshots (this is the shrink bug: digests dropped to 2-8
    # stories for sources whose front page stays roughly constant).
    save_snapshot(
        SourceSnapshot(
            source="github",
            date=date(2026, 8, 1),
            stories=[
                Story(
                    source="github",
                    title=f"Repo{i}",
                    url=f"https://g/{i}",
                    score=50 - i,
                )
                for i in range(5)
            ],
        ),
        tmp_path,
    )
    save_snapshot(
        SourceSnapshot(
            source="github",
            date=date(2026, 8, 2),
            stories=[
                Story(
                    source="github",
                    title=f"Repo{i}",
                    url=f"https://g/{i}",
                    score=50 - i,
                )
                for i in range(5)
            ],
        ),
        tmp_path,
    )
    digest = combined_digest(tmp_path)
    assert digest is not None
    assert len(digest.stories) >= 5


def test_corrupt_snapshot_does_not_break_site(tmp_path):
    from app.store import load_all_snapshots, load_snapshot

    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 2),
            stories=[Story(source="hn", title="A", url="https://a")],
        ),
        tmp_path,
    )
    # A corrupt archive file (truncated write, hand edit) must be skipped, not
    # explode the build or the dev server.
    (tmp_path / "source_hn_2026-08-03.json").write_text("{not json")

    assert load_snapshot("hn", date(2026, 8, 3), tmp_path) is None
    assert [s.date for s in load_all_snapshots(tmp_path)] == [date(2026, 8, 2)]


def test_source_with_no_label_or_tag_gets_key_fallback(tmp_path):
    from app.config import load_sources

    yaml_file = tmp_path / "sources.yaml"
    yaml_file.write_text(
        """
sources:
  - key: blog
    type: rss
    url: https://example.com/feed
    boolish_weekday: "nine"
    weekday: 42
"""
    )
    sources = load_sources(yaml_file)
    assert sources["blog"]["label"] == "blog"
    assert sources["blog"]["tag"] == "blog"
    # An out-of-range weekday is dropped so cadence is never weekly · 42.
    assert sources["blog"]["weekday"] is None


def test_build_survives_residual_source_not_in_config(tmp_path):
    from scripts.build_site import build_site

    # A snapshot for a source that has since been removed from sources.yaml;
    # `ghost` is not a config source, so builds rely on the label/tag fallback.
    save_snapshot(
        SourceSnapshot(
            source="ghost",
            date=date(2026, 8, 2),
            stories=[Story(source="ghost", title="Leftover", url="https://g")],
        ),
        tmp_path,
    )
    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 2),
            stories=[Story(source="hn", title="Live", url="https://hn")],
        ),
        tmp_path,
    )
    out = tmp_path / "site_ghost"
    build_site(tmp_path, out, "/catnews", "https://example.com")

    page = (out / "archive" / "ghost" / "2026-08-02" / "index.html").read_text()
    assert "Leftover" in page
    feed = (out / "feed-ghost.rss").read_text()
    assert "Leftover" in feed
    stats = (out / "stats" / "index.html").read_text()
    # The stats page lists per-source rows, not story titles: the ghost row
    # must render via the key fallback rather than a KeyError.
    assert "ghost" in stats
    assert "Leftover" in (out / "api" / "stories.json").read_text()


def test_ghost_source_stats_page_renders(client, tmp_path):
    save_snapshot(
        SourceSnapshot(
            source="ghost",
            date=date(2026, 8, 2),
            stories=[Story(source="ghost", title="Leftover", url="https://g")],
        ),
        tmp_path,
    )
    assert client.get("/stats/").status_code == 200
    assert client.get("/archive/").status_code == 200


def test_hex_rgb_handles_named_and_short_colors():
    from app.config import source_accent_rgb
    from app.og_image import hex_rgb

    assert hex_rgb("#123456") == (0x12, 0x34, 0x56)
    assert hex_rgb("abc") == (0xAA, 0xBB, 0xCC)
    assert hex_rgb("rebeccapurple") is None
    assert hex_rgb("") is None

    # A named-color source override previously crashed the OG renderer.
    from app.config import badge_color

    original = {"type": "builtin", "label": "X", "tag": "x", "color": "rebeccapurple"}
    from app import config as config_module

    config_module.SOURCES["tint"] = original
    try:
        assert source_accent_rgb("tint") == (0x3B, 0x3E, 0x37)
        assert badge_color("tint") == ("rebeccapurple",) * 4
    finally:
        config_module.SOURCES.pop("tint", None)


def test_feed_redirect_honors_base_path(client, tmp_path, monkeypatch):
    from app import main as app_main

    save_snapshot(
        SourceSnapshot(
            source="hn",
            date=date(2026, 8, 2),
            stories=[Story(source="hn", title="A", url="https://a")],
        ),
        tmp_path,
    )
    monkeypatch.setattr(app_main, "BASE_PATH", "/catnews")
    resp = client.get("/feed", follow_redirects=False)
    assert resp.status_code == 307 or resp.status_code == 302
    assert resp.headers["location"] == "/catnews/feed.rss"


def test_parse_links_accepts_single_quoted_hrefs():
    html = """<p>Read <a href=\'https://example.com/a\'>the post</a> and
    <a href="https://example.com/b">the other</a>.</p>"""
    links = parse_links(html)
    assert [l.url for l in links] == ["https://example.com/a", "https://example.com/b"]
