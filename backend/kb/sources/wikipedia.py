"""Wikipedia articles (CC BY-SA 4.0: credit the article and keep adapted text under the same licence)."""
from __future__ import annotations

from urllib.parse import quote

from . import SourceDoc, http_client

API = "https://en.wikipedia.org/w/api.php"


def fetch_article(title: str, domain: str | None = None, max_chars: int = 12000) -> SourceDoc | None:
    params = {
        "action": "query", "format": "json", "formatversion": "2", "redirects": "1",
        "prop": "extracts|info", "explaintext": "1", "inprop": "url", "titles": title,
    }
    with http_client() as client:
        data = client.get(API, params=params).json()
    pages = data.get("query", {}).get("pages", [])
    if not pages or pages[0].get("missing"):
        return None
    page = pages[0]
    text = page.get("extract", "")[:max_chars]
    if not text:
        return None
    url = page.get("fullurl") or f"https://en.wikipedia.org/wiki/{quote(page['title'].replace(' ', '_'))}"
    return SourceDoc(url=url, title=f"Wikipedia: {page['title']}", kind="wiki", licence="CC BY-SA 4.0",
                     publisher="Wikipedia", text=text, domain=domain)


def search_titles(query: str, limit: int = 5) -> list[str]:
    params = {"action": "query", "format": "json", "list": "search", "srsearch": query, "srlimit": limit}
    with http_client() as client:
        data = client.get(API, params=params).json()
    return [hit["title"] for hit in data.get("query", {}).get("search", [])]
