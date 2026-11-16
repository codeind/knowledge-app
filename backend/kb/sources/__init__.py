"""Source fetchers. Each returns SourceDoc objects: text plus the licence that says how it may be used."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import httpx

from ..config import get_settings


@dataclass
class SourceDoc:
    url: str
    title: str
    kind: str                 # wiki | book | news | law | data
    licence: str              # "CC BY-SA 4.0" | "Public domain" | "Link only" | ...
    publisher: str | None = None
    text: str = ""
    published: str | None = None   # ISO date
    domain: str | None = None
    meta: dict = field(default_factory=dict)

    @property
    def link_only(self) -> bool:
        return self.licence.lower().startswith("link only")


def http_client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": get_settings().user_agent},
        timeout=httpx.Timeout(20.0),
        follow_redirects=True,
        event_hooks={"response": [lambda r: r.raise_for_status()]},  # never parse an error page as content
    )


def chunk_text(text: str, max_words: int = 180, max_chunks: int = 12) -> list[str]:
    """Split text into paragraph-aligned chunks of roughly max_words words."""
    paras = [p.strip() for p in re.split(r"\n\s*\n|\n(?==)", text) if p.strip() and not p.strip().startswith("==")]
    chunks: list[str] = []
    current: list[str] = []
    count = 0
    for para in paras:
        words = para.split()
        if count + len(words) > max_words and current:
            chunks.append(" ".join(current))
            current, count = [], 0
        current.extend(words)
        count += len(words)
        if len(chunks) >= max_chunks:
            break
    if current and len(chunks) < max_chunks:
        chunks.append(" ".join(current))
    return chunks
