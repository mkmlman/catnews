from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime
from html import unescape

from ..config import REQUEST_TIMEOUT
from ..models import Story

ARXIV_API_URL = "https://export.arxiv.org/api/query"

# Categories worth a digest for engineers.
CATEGORIES = "cs.AI cs.CL cs.LG cs.SE cs.DB cs.CR cs.DC cs.NE"
NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

MAX_SUMMARY_CHARS = 900


async def fetch_arxiv(client) -> list[Story]:
    """Fetch the latest papers from a handful of cs categories via the arXiv export API."""
    params = {
        "search_query": " OR ".join(f"cat:{c}" for c in CATEGORIES.split()),
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": 40,
    }
    response = await client.get(ARXIV_API_URL, params=params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    root = ET.fromstring(response.text)
    stories = [parse_entry(entry) for entry in root.findall("atom:entry", NS)]
    return [s for s in stories if s]


def parse_entry(entry: ET.Element) -> Story | None:
    def text(tag: str) -> str | None:
        node = entry.find(f"atom:{tag}", NS)
        return (node.text or "").strip() if node is not None and node.text else None

    title = unescape(text("title") or "").replace("\n", " ")
    if not title:
        return None
    id_url = (entry.findtext("atom:id", default="", namespaces=NS) or "").strip()
    published_raw = text("published")
    published = None
    if published_raw:
        try:
            published = datetime.fromisoformat(published_raw)
        except ValueError:
            pass

    authors = [
        a.findtext("atom:name", default="", namespaces=NS).strip()
        for a in entry.findall("atom:author", NS)
    ]
    authors = [a for a in authors if a]
    summary = unescape(text("summary") or "").strip().replace("\n", " ")

    external_id = id_url.rstrip("/").split("/abs/")[-1] if "/abs/" in id_url else None

    return Story(
        source="arxiv",
        title=title,
        url=id_url or f"https://arxiv.org/abs/{external_id}",
        authors=authors,
        author=authors[0] if authors else None,
        byline=authors[0] if authors else None,
        external_id=external_id,
        published=published,
        snippet=summary[:MAX_SUMMARY_CHARS] if summary else None,
    )
