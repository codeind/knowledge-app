"""Load the sample cards in seed_data.json (safe to run more than once)."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from . import db

SEED_PATH = Path(__file__).with_name("seed_data.json")


def load_seed(conn: sqlite3.Connection, path: Path = SEED_PATH) -> dict[str, int]:
    data = json.loads(path.read_text())
    source_ids = {key: db.upsert_source(conn, **src) for key, src in data["sources"].items()}

    story_ids: dict[str, int] = {}
    for key, title in data["stories"].items():
        row = conn.execute("SELECT id FROM stories WHERE title = ?", (title,)).fetchone()
        story_ids[key] = row["id"] if row else conn.execute(
            "INSERT INTO stories (title) VALUES (?) RETURNING id", (title,)).fetchone()["id"]

    book_ids = {}
    for book in data["books"]:
        book_ids[book["key"]] = db.upsert_book(
            conn, title=book["title"], url=book["url"], public_domain=book["public_domain"],
            author=book.get("author"), year=book.get("year"), subjects=book.get("subjects", []))

    card_ids: dict[str, int] = {}
    added = 0
    for spec in data["cards"]:
        row = conn.execute("SELECT id FROM cards WHERE section = ? AND domain = ? AND title = ?",
                           (spec["section"], spec["domain"], spec["title"])).fetchone()
        if row:
            card_ids[spec["key"]] = row["id"]
            continue
        card = {
            **{k: v for k, v in spec.items() if k not in {"key", "story", "entities", "sources", "links"}},
            "story_id": story_ids.get(spec.get("story")),
            "entities": [{"name": n, "kind": k} for n, k in spec.get("entities", [])],
            "source_ids": [source_ids[s] for s in spec.get("sources", [])],
            "origin": "seed",
            "verification": "unverified",
            "status": "published",
        }
        card_ids[spec["key"]] = db.insert_card(conn, card)
        added += 1

    links = 0
    for spec in data["cards"]:
        for relation, target in spec.get("links", []):
            db.add_link(conn, card_ids[spec["key"]], card_ids[target], relation, score=1.0, manual=True)
            links += 1
    conn.commit()
    return {"cards_added": added, "cards_total": len(card_ids), "manual_links": links, "books": len(book_ids)}
