"""Builds the Go deeper links between cards.

For each news card it finds:
- the story it belongs to (earlier news cards about the same thing) -> backstory timeline
- related coverage (similar news that is not the same story)
- key players (profile cards for entities the card mentions)
- explainers (Learn cards on the concepts involved)
- viewpoints (viewpoint cards on the debate around it)
- books (public-domain first, then title-only links)

Similarity is TF-IDF over title, body, tags and entity names: cheap, transparent, no embeddings API
needed. Swap in embeddings later without changing the tables.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from . import db
from .config import get_settings

EXPLAINER_TYPES = {"concept", "lesson", "law", "event"}
MIN_RELATED = 0.12
MIN_EXPLAINER = 0.10


def _card_docs(conn: sqlite3.Connection) -> tuple[list[dict[str, Any]], list[str]]:
    rows = conn.execute(f"SELECT {db.CARD_COLUMNS} FROM cards WHERE status = 'published'").fetchall()
    cards = [db.row_to_card(conn, r) for r in rows]
    texts = []
    for c in cards:
        ents = " ".join(e["name"] for e in c["entities"])
        tags = " ".join(c["tags"])
        texts.append(f"{c['title']} {c['title']} {c['body']} {tags} {tags} {ents} {ents}")
    return cards, texts


def _entity_names(card: dict[str, Any]) -> set[str]:
    return {e["name"].lower() for e in card["entities"]}


def rebuild_links(conn: sqlite3.Connection) -> dict[str, int]:
    """Recompute stories, card_links and card_books for all published cards."""
    settings = get_settings()
    cards, texts = _card_docs(conn)
    if len(cards) < 2:
        return {"links": 0, "stories": 0}
    matrix = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1, sublinear_tf=True).fit_transform(texts)
    sim = cosine_similarity(matrix)
    index = {c["id"]: i for i, c in enumerate(cards)}

    conn.execute("DELETE FROM card_links WHERE manual = 0")
    link_count = 0
    news = sorted((c for c in cards if c["section"] == "news"), key=lambda c: c["event_date"] or "")

    # Stories: walk news in date order; join the story of the most similar earlier card that shares an entity.
    for card in news:
        if card["origin"] == "seed" and card["story_id"]:
            continue  # seed data carries hand-set stories
        i = index[card["id"]]
        best, best_score = None, 0.0
        for other in news:
            if other["id"] == card["id"] or (other["event_date"] or "") > (card["event_date"] or ""):
                continue
            score = float(sim[i, index[other["id"]]])
            if score >= settings.story_threshold and _entity_names(card) & _entity_names(other) and score > best_score:
                best, best_score = other, score
        if best:
            story_id = best["story_id"]
            if not story_id:
                story_id = conn.execute("INSERT INTO stories (title) VALUES (?) RETURNING id",
                                        (best["title"],)).fetchone()["id"]
                conn.execute("UPDATE cards SET story_id = ? WHERE id = ?", (story_id, best["id"]))
                best["story_id"] = story_id
            conn.execute("UPDATE cards SET story_id = ? WHERE id = ?", (story_id, card["id"]))
            card["story_id"] = story_id

    for card in cards:
        i = index[card["id"]]
        ents = _entity_names(card)
        tags = set(card["tags"])
        for other in cards:
            if other["id"] == card["id"]:
                continue
            score = float(sim[i, index[other["id"]]])
            shared_ent = bool(ents & _entity_names(other))
            shared_tag = bool(tags & set(other["tags"]))
            if other["card_type"] == "profile":
                if any(e in other["title"].lower() for e in ents) or shared_ent:
                    db.add_link(conn, card["id"], other["id"], "player", score)
                    link_count += 1
            elif other["card_type"] == "viewpoint":
                if score >= MIN_EXPLAINER or (shared_tag and shared_ent):
                    db.add_link(conn, card["id"], other["id"], "viewpoint", score)
                    link_count += 1
            elif other["section"] == "learn" and other["card_type"] in EXPLAINER_TYPES:
                if score >= MIN_EXPLAINER or (shared_tag and score >= MIN_EXPLAINER / 2):
                    db.add_link(conn, card["id"], other["id"], "explainer", score)
                    link_count += 1
            elif other["section"] == "news" and card["section"] == "news":
                same_story = card["story_id"] and card["story_id"] == other["story_id"]
                if not same_story and (score >= MIN_RELATED or (shared_ent and score >= MIN_RELATED / 2)):
                    db.add_link(conn, card["id"], other["id"], "related", score)
                    link_count += 1

    # Books: match subjects against tags (and entity names).
    books = [dict(r) for r in conn.execute("SELECT id, subjects FROM books")]
    for card in cards:
        keys = set(card["tags"]) | _entity_names(card)
        for book in books:
            subjects = {s.strip() for s in book["subjects"].split(",") if s.strip()}
            if keys & subjects:
                conn.execute("INSERT INTO card_books (card_id, book_id) VALUES (?, ?) ON CONFLICT DO NOTHING",
                             (card["id"], book["id"]))
    conn.commit()
    stories = conn.execute("SELECT COUNT(*) FROM stories").fetchone()[0]
    return {"links": link_count, "stories": stories}


def _linked(conn: sqlite3.Connection, card_id: int, relation: str, limit: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        f"""SELECT {', '.join('c.' + col.strip() for col in db.CARD_COLUMNS.split(','))}, l.score
            FROM card_links l JOIN cards c ON c.id = l.to_id
            WHERE l.from_id = ? AND l.relation = ? AND c.status = 'published'
            ORDER BY l.score DESC LIMIT ?""",
        (card_id, relation, limit),
    ).fetchall()
    return [db.row_to_card(conn, r) for r in rows]


def go_deeper(conn: sqlite3.Connection, card_id: int) -> dict[str, Any] | None:
    card = db.get_card(conn, card_id, full=False)
    if not card:
        return None
    timeline: list[dict[str, Any]] = []
    if card["story_id"]:
        timeline = db.query_cards(conn, "story_id = ?", (card["story_id"],), order="event_date ASC", limit=50)
    timeline_ids = {c["id"] for c in timeline}
    related = [c for c in _linked(conn, card_id, "related", 8) if c["id"] not in timeline_ids]
    # Dated Learn events on the same topic also belong on the timeline.
    explainers = _linked(conn, card_id, "explainer", 8)
    for ex in explainers:
        if ex["card_type"] == "event" and ex["event_date"] and ex["id"] not in timeline_ids:
            timeline.append(ex)
            timeline_ids.add(ex["id"])
    timeline.sort(key=lambda c: c["event_date"] or "")
    explainers = [e for e in explainers if e["id"] not in timeline_ids]
    result = {
        "card": card,
        "timeline": timeline,
        "related": related,
        "players": _linked(conn, card_id, "player", 5),
        "explainers": explainers,
        "viewpoints": _linked(conn, card_id, "viewpoint", 6),
        "books": db.books_for_card(conn, card_id),
    }
    result["has_depth"] = bool(len(timeline) > 1 or related or result["players"] or explainers
                               or result["viewpoints"] or result["books"])
    return result


def depth_flags(conn: sqlite3.Connection, card_ids: list[int]) -> dict[int, bool]:
    """Which cards get a Go deeper button (cheap check for feed pages)."""
    if not card_ids:
        return {}
    marks = ",".join("?" * len(card_ids))
    flags = {cid: False for cid in card_ids}
    for r in conn.execute(f"SELECT DISTINCT from_id FROM card_links WHERE from_id IN ({marks})", card_ids):
        flags[r["from_id"]] = True
    for r in conn.execute(f"SELECT DISTINCT card_id FROM card_books WHERE card_id IN ({marks})", card_ids):
        flags[r["card_id"]] = True
    for r in conn.execute(
        f"""SELECT c.id FROM cards c WHERE c.id IN ({marks}) AND c.story_id IS NOT NULL AND
            (SELECT COUNT(*) FROM cards o WHERE o.story_id = c.story_id AND o.status = 'published') > 1""",
        card_ids,
    ):
        flags[r["id"]] = True
    return flags
