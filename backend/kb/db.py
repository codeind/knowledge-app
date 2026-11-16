"""Database access shared by the pipeline and the API.

Two back ends, one set of SQL:
- SQLite (default): a local file, zero setup, used for development and tests.
- Postgres (set DATABASE_URL=postgresql://...): used in the cloud (e.g. Neon).

The SQL in this package is written to run on both (ON CONFLICT, RETURNING, CURRENT_TIMESTAMP).
The Postgres wrapper only converts `?` placeholders to `%s` and returns rows that work like sqlite3.Row.
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator

from .config import get_settings

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
PG_SCHEMA_PATH = Path(__file__).with_name("schema_pg.sql")


class Row(dict):
    """A dict that also allows row[0]-style access, like sqlite3.Row."""

    def __getitem__(self, key):  # type: ignore[override]
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


class PgConnection:
    """Minimal sqlite3-like wrapper around a psycopg connection."""

    is_pg = True

    def __init__(self, url: str):
        import psycopg

        def row_factory(cursor):
            names = [c.name for c in cursor.description] if cursor.description else []
            return lambda values: Row(zip(names, values))

        self._conn = psycopg.connect(url, row_factory=row_factory)

    def execute(self, sql: str, params: Iterable[Any] = ()):
        params = tuple(params)
        if not params:  # no placeholders to convert; a literal % stays as it is
            return self._conn.execute(sql)
        return self._conn.execute(sql.replace("%", "%%").replace("?", "%s"), params)

    def executescript(self, script: str) -> None:
        self._conn.execute(script)

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()


def database_url() -> str | None:
    url = os.getenv("DATABASE_URL", "").strip()
    return url if url.startswith(("postgres://", "postgresql://")) else None


def connect(db_path: Path | str | None = None):
    """Postgres when DATABASE_URL is set (and no explicit SQLite path is given), else SQLite."""
    url = database_url()
    if url and db_path is None:
        return PgConnection(url)
    path = Path(db_path) if db_path else get_settings().db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn) -> None:
    if getattr(conn, "is_pg", False):
        conn.executescript(PG_SCHEMA_PATH.read_text())
    else:
        conn.executescript(SCHEMA_PATH.read_text())
    conn.commit()


@contextmanager
def transaction(conn) -> Iterator[Any]:
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


# ---------- writes ----------

def upsert_source(conn: sqlite3.Connection, *, url: str, title: str, kind: str, licence: str,
                  publisher: str | None = None) -> int:
    conn.execute(
        """INSERT INTO sources (url, title, publisher, kind, licence) VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(url) DO UPDATE SET title = excluded.title, publisher = excluded.publisher,
           licence = excluded.licence""",
        (url, title, publisher, kind, licence),
    )
    return conn.execute("SELECT id FROM sources WHERE url = ?", (url,)).fetchone()["id"]


def add_passages(conn: sqlite3.Connection, source_id: int, texts: Iterable[str]) -> list[int]:
    ids = []
    for idx, text in enumerate(texts):
        conn.execute(
            """INSERT INTO passages (source_id, idx, text) VALUES (?, ?, ?)
               ON CONFLICT(source_id, idx) DO UPDATE SET text = excluded.text""",
            (source_id, idx, text),
        )
        ids.append(conn.execute(
            "SELECT id FROM passages WHERE source_id = ? AND idx = ?", (source_id, idx)).fetchone()["id"])
    return ids


def entity_id(conn: sqlite3.Connection, name: str, kind: str = "other") -> int:
    conn.execute("INSERT INTO entities (name, kind) VALUES (?, ?) ON CONFLICT DO NOTHING", (name.strip(), kind))
    return conn.execute("SELECT id FROM entities WHERE LOWER(name) = LOWER(?)", (name.strip(),)).fetchone()["id"]


def upsert_book(conn: sqlite3.Connection, *, title: str, url: str, public_domain: bool,
                author: str | None = None, year: int | None = None, subjects: Iterable[str] = ()) -> int:
    conn.execute(
        """INSERT INTO books (title, author, year, url, public_domain, subjects) VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(url) DO UPDATE SET subjects = excluded.subjects""",
        (title, author, year, url, int(public_domain), ",".join(s.lower() for s in subjects)),
    )
    return conn.execute("SELECT id FROM books WHERE url = ?", (url,)).fetchone()["id"]


def card_exists(conn: sqlite3.Connection, section: str, domain: str, title: str) -> bool:
    return conn.execute("SELECT 1 FROM cards WHERE section = ? AND domain = ? AND title = ?",
                        (section, domain, title)).fetchone() is not None


def insert_card(conn: sqlite3.Connection, card: dict[str, Any]) -> int:
    """Insert a card with its tags, entities, claims and sources. Returns the card id.

    Expected keys: section, domain, card_type, title, body; optional: label, viewpoint, verification,
    status, quality_score, event_date, story_id, track_order, origin, tags, entities
    ([{name, kind}]), claims ([{text, passage_ids, verdict}]), source_ids, book_ids.
    """
    cur = conn.execute(
        """INSERT INTO cards (section, domain, card_type, title, body, label, viewpoint, verification,
                              status, quality_score, event_date, story_id, track_order, origin)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id""",
        (
            card["section"], card["domain"], card["card_type"], card["title"].strip(), card["body"].strip(),
            card.get("label", "Fact"), card.get("viewpoint"), card.get("verification", "unverified"),
            card.get("status", "published"), card.get("quality_score"), card.get("event_date"),
            card.get("story_id"), card.get("track_order"), card.get("origin", "pipeline"),
        ),
    )
    card_id = cur.fetchone()["id"]
    for tag in {t.strip().lower() for t in card.get("tags", []) if t.strip()}:
        conn.execute("INSERT INTO card_tags (card_id, tag) VALUES (?, ?) ON CONFLICT DO NOTHING", (card_id, tag))
    for ent in card.get("entities", []):
        eid = entity_id(conn, ent["name"], ent.get("kind", "other"))
        conn.execute("INSERT INTO card_entities (card_id, entity_id) VALUES (?, ?) ON CONFLICT DO NOTHING", (card_id, eid))
    for claim in card.get("claims", []):
        conn.execute(
            "INSERT INTO card_claims (card_id, claim, passage_ids, verdict) VALUES (?, ?, ?, ?)",
            (card_id, claim["text"], json.dumps(claim.get("passage_ids", [])), claim.get("verdict", "unchecked")),
        )
    for sid in set(card.get("source_ids", [])):
        conn.execute("INSERT INTO card_sources (card_id, source_id) VALUES (?, ?) ON CONFLICT DO NOTHING", (card_id, sid))
    for bid in set(card.get("book_ids", [])):
        conn.execute("INSERT INTO card_books (card_id, book_id) VALUES (?, ?) ON CONFLICT DO NOTHING", (card_id, bid))
    return card_id


def add_link(conn: sqlite3.Connection, from_id: int, to_id: int, relation: str, score: float | None = None,
             manual: bool = False) -> None:
    if from_id == to_id:
        return
    conn.execute(
        """INSERT INTO card_links (from_id, to_id, relation, score, manual) VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(from_id, to_id, relation) DO UPDATE SET
           score = CASE WHEN COALESCE(excluded.score, 0) > COALESCE(card_links.score, 0)
                        THEN excluded.score ELSE card_links.score END,
           manual = CASE WHEN excluded.manual > card_links.manual THEN excluded.manual ELSE card_links.manual END""",
        (from_id, to_id, relation, score, int(manual)),
    )


# ---------- reads ----------

CARD_COLUMNS = ("id, section, domain, card_type, title, body, label, viewpoint, verification, status, "
                "quality_score, event_date, story_id, track_order, origin, created_at")


def _card_extras(conn: sqlite3.Connection, card: dict[str, Any], full: bool) -> dict[str, Any]:
    cid = card["id"]
    card["tags"] = [r["tag"] for r in conn.execute(
        "SELECT tag FROM card_tags WHERE card_id = ? ORDER BY tag", (cid,))]
    card["entities"] = [dict(r) for r in conn.execute(
        """SELECT e.name, e.kind FROM entities e JOIN card_entities ce ON ce.entity_id = e.id
           WHERE ce.card_id = ? ORDER BY e.name""", (cid,))]
    card["sources"] = [dict(r) for r in conn.execute(
        """SELECT s.id, s.url, s.title, s.publisher, s.kind, s.licence FROM sources s
           JOIN card_sources cs ON cs.source_id = s.id WHERE cs.card_id = ? ORDER BY s.title""", (cid,))]
    if full:
        claims = []
        for r in conn.execute("SELECT claim, passage_ids, verdict FROM card_claims WHERE card_id = ?", (cid,)):
            claims.append({"text": r["claim"], "passage_ids": json.loads(r["passage_ids"]), "verdict": r["verdict"]})
        card["claims"] = claims
    return card


def row_to_card(conn: sqlite3.Connection, row: Any, full: bool = False) -> dict[str, Any]:
    return _card_extras(conn, dict(row), full)


def get_card(conn: sqlite3.Connection, card_id: int, full: bool = True) -> dict[str, Any] | None:
    row = conn.execute(f"SELECT {CARD_COLUMNS} FROM cards WHERE id = ?", (card_id,)).fetchone()
    return row_to_card(conn, row, full) if row else None


def query_cards(conn: sqlite3.Connection, where: str = "1=1", params: tuple = (), order: str = "id DESC",
                limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    rows = conn.execute(
        f"SELECT {CARD_COLUMNS} FROM cards WHERE status = 'published' AND ({where}) "
        f"ORDER BY {order} LIMIT ? OFFSET ?",
        (*params, limit, offset),
    ).fetchall()
    return [row_to_card(conn, r) for r in rows]


def books_for_card(conn: sqlite3.Connection, card_id: int) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(
        """SELECT b.* FROM books b JOIN card_books cb ON cb.book_id = b.id WHERE cb.card_id = ?
           ORDER BY b.public_domain DESC, b.title""", (card_id,))]
