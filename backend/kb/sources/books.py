"""Books.

- Public-domain books come from Project Gutenberg through the Gutendex API. Only books Gutendex marks
  as not under copyright are used, and their text may be summarised into cards.
- Newer books come from Open Library as metadata only (title, author, link). No text is fetched,
  so they can only be shown as a title link.
"""
from __future__ import annotations

from . import SourceDoc, chunk_text, http_client

GUTENDEX = "https://gutendex.com/books"
OPEN_LIBRARY = "https://openlibrary.org/search.json"


def search_public_domain(query: str, limit: int = 3) -> list[dict]:
    with http_client() as client:
        data = client.get(GUTENDEX, params={"search": query, "languages": "en"}).json()
    books = []
    for item in data.get("results", []):
        if item.get("copyright") is not False:   # skip anything not clearly public domain
            continue
        authors = item.get("authors") or [{}]
        books.append({
            "title": item["title"],
            "author": authors[0].get("name"),
            "year": None,
            "url": f"https://www.gutenberg.org/ebooks/{item['id']}",
            "public_domain": True,
            "subjects": [s.split(" -- ")[0].lower() for s in item.get("subjects", [])][:6],
            "text_url": _plain_text_url(item.get("formats", {})),
        })
        if len(books) >= limit:
            break
    return books


def _plain_text_url(formats: dict) -> str | None:
    for key, url in formats.items():
        if key.startswith("text/plain"):
            return url
    return None


def fetch_book_excerpt(book: dict, start_word: int = 3000, words: int = 2500) -> SourceDoc | None:
    """Fetch part of a public-domain book's text (skipping the Gutenberg header)."""
    if not book.get("public_domain") or not book.get("text_url"):
        return None
    with http_client() as client:
        text = client.get(book["text_url"]).text
    marker = "*** START OF"
    if marker in text:
        text = text.split(marker, 1)[1].split("\n", 1)[-1]
    excerpt = " ".join(text.split()[start_word:start_word + words])
    return SourceDoc(url=book["url"], title=f"{book['title']} ({book.get('author') or 'unknown'})", kind="book",
                     licence="Public domain", publisher="Project Gutenberg", text=excerpt)


def search_modern_titles(query: str, limit: int = 3) -> list[dict]:
    """Metadata only, for 'further reading' links. Never fetch or summarise these books' text."""
    with http_client() as client:
        data = client.get(OPEN_LIBRARY, params={"q": query, "limit": limit,
                                                "fields": "key,title,author_name,first_publish_year"}).json()
    return [{
        "title": d["title"],
        "author": (d.get("author_name") or [None])[0],
        "year": d.get("first_publish_year"),
        "url": f"https://openlibrary.org{d['key']}",
        "public_domain": False,
        "subjects": [query.lower()],
    } for d in data.get("docs", [])]


def excerpt_passages(doc: SourceDoc) -> list[str]:
    return chunk_text(doc.text, max_words=200, max_chunks=8)
