"""News from RSS feeds.

Feeds from public-domain publishers (US government agencies) can be summarised in full.
For any other outlet, set licence to "Link only": the app keeps only the headline, the feed's short
summary and the link, and the card must send readers to the original article.
"""
from __future__ import annotations

import html
import re
from datetime import datetime
from time import mktime

import feedparser

from . import SourceDoc, http_client

_TAG = re.compile(r"<[^>]+>")


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAG.sub(" ", text or ""))).strip()


def fetch_feed(url: str, *, publisher: str, licence: str, domain: str, limit: int = 10) -> list[SourceDoc]:
    with http_client() as client:
        raw = client.get(url).content
    parsed = feedparser.parse(raw)
    docs = []
    for entry in parsed.entries[:limit]:
        published = None
        stamp = entry.get("published_parsed") or entry.get("updated_parsed")
        if stamp:
            published = datetime.fromtimestamp(mktime(stamp)).date().isoformat()
        summary = _clean(entry.get("summary", ""))
        content = ""
        if entry.get("content") and not licence.lower().startswith("link only"):
            content = _clean(entry["content"][0].get("value", ""))
        text = content or summary
        if licence.lower().startswith("link only"):
            text = " ".join(summary.split()[:60])
        if not text:
            continue
        docs.append(SourceDoc(url=entry.get("link", url), title=_clean(entry.get("title", "Untitled")),
                              kind="news", licence=licence, publisher=publisher, text=text,
                              published=published, domain=domain))
    return docs
