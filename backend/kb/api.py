"""HTTP API for the web app.

Run:  uvicorn kb.api:app --reload --port 8000   (from the backend/ folder)
Docs: http://localhost:8000/docs
"""
from __future__ import annotations

import os
import sqlite3
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import db
from .cli import stats as kb_stats
from .linking import depth_flags, go_deeper

DOMAINS = {
    "history": "History",
    "ancient_history": "Ancient history",
    "economics": "Economics",
    "sports": "Sports",
    "laws_us": "Laws: United States",
    "laws_in": "Laws: India",
    "science": "Science and space",
}

app = FastAPI(title="AI Knowledge App API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("KB_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

_conn = None          # tests can set a shared connection here
_db_ready = False


def _prepare_database() -> None:
    """Create tables and load the sample cards on first start (safe to repeat)."""
    global _db_ready
    if _db_ready:
        return
    conn = db.connect()
    try:
        db.init_db(conn)
        if conn.execute("SELECT COUNT(*) AS n FROM cards").fetchone()["n"] == 0:
            from .linking import rebuild_links
            from .seed import load_seed

            load_seed(conn)
            rebuild_links(conn)
    finally:
        conn.close()
    _db_ready = True


def get_conn():
    """One connection per request: safe for serverless Postgres that drops idle connections."""
    if _conn is not None:
        yield _conn
        return
    _prepare_database()
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()


def _with_depth(conn: sqlite3.Connection, cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flags = depth_flags(conn, [c["id"] for c in cards])
    saved = {r["card_id"] for r in conn.execute("SELECT card_id FROM saves WHERE user_id = 'local'")}
    for c in cards:
        c["has_depth"] = flags.get(c["id"], False)
        c["saved"] = c["id"] in saved
    return cards


@app.get("/api/health")
def health(conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    count = conn.execute("SELECT COUNT(*) AS n FROM cards WHERE status = 'published'").fetchone()["n"]
    return {"ok": True, "published_cards": count}


@app.get("/api/news")
def news(domain: str | None = None, limit: int = Query(20, le=100), offset: int = 0,
         conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    where, params = "section = 'news'", ()
    if domain:
        where, params = where + " AND domain = ?", (domain,)
    cards = db.query_cards(conn, where, params, order="COALESCE(event_date, created_at) DESC, id DESC",
                           limit=limit, offset=offset)
    return {"cards": _with_depth(conn, cards)}


@app.get("/api/cards/{card_id}")
def card(card_id: int, conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    found = db.get_card(conn, card_id, full=True)
    if not found or found["status"] != "published":
        raise HTTPException(404, "Card not found")
    return _with_depth(conn, [found])[0]


@app.get("/api/cards/{card_id}/deeper")
def deeper(card_id: int, conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    result = go_deeper(conn, card_id)
    if not result:
        raise HTTPException(404, "Card not found")
    return result


@app.get("/api/learn/tracks")
def tracks(conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    counts = {r["domain"]: r["n"] for r in conn.execute(
        "SELECT domain, COUNT(*) n FROM cards WHERE section = 'learn' AND status = 'published' GROUP BY domain")}
    return {"tracks": [{"domain": d, "name": name, "cards": counts.get(d, 0)} for d, name in DOMAINS.items()]}


@app.get("/api/learn/{domain}")
def learn(domain: str, card_type: str | None = None, conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    if domain not in DOMAINS:
        raise HTTPException(404, "Unknown track")
    where, params = "section = 'learn' AND domain = ?", (domain,)
    if card_type:
        where, params = where + " AND card_type = ?", (*params, card_type)
    cards = db.query_cards(conn, where, params, order="COALESCE(track_order, 9999), event_date, id", limit=200)
    return {"domain": domain, "name": DOMAINS[domain], "cards": _with_depth(conn, cards)}


@app.get("/api/search")
def search(q: str = Query(..., min_length=2), conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    like = f"%{q.lower()}%"
    cards = db.query_cards(
        conn,
        "LOWER(title) LIKE ? OR LOWER(body) LIKE ? OR id IN (SELECT card_id FROM card_tags WHERE LOWER(tag) LIKE ?)",
        (like, like, like), order="section DESC, id DESC", limit=40)
    return {"query": q, "cards": _with_depth(conn, cards)}


class SaveIn(BaseModel):
    card_id: int


@app.get("/api/saves")
def list_saves(conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    cards = db.query_cards(conn, "id IN (SELECT card_id FROM saves WHERE user_id = 'local')", limit=200)
    return {"cards": _with_depth(conn, cards)}


@app.post("/api/saves")
def add_save(body: SaveIn, conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    if not db.get_card(conn, body.card_id, full=False):
        raise HTTPException(404, "Card not found")
    conn.execute("INSERT INTO saves (user_id, card_id) VALUES ('local', ?) ON CONFLICT DO NOTHING", (body.card_id,))
    conn.commit()
    return {"saved": True}


@app.delete("/api/saves/{card_id}")
def remove_save(card_id: int, conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    conn.execute("DELETE FROM saves WHERE user_id = 'local' AND card_id = ?", (card_id,))
    conn.commit()
    return {"saved": False}


@app.get("/api/stats")
def stats(conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    result = kb_stats(conn)
    result["recent_runs"] = [dict(r) for r in conn.execute(
        "SELECT job, started_at, cards_drafted, cards_published, cards_rejected FROM pipeline_runs "
        "ORDER BY id DESC LIMIT 10")]
    return result


# Serve the pre-built website (web/out copied to backend/site) so the whole app runs with Python only.
# Mounted last so the /api routes above take priority.
from pathlib import Path  # noqa: E402

from fastapi.staticfiles import StaticFiles  # noqa: E402

SITE_DIR = Path(__file__).resolve().parent.parent / "site"
if SITE_DIR.is_dir():
    app.mount("/", StaticFiles(directory=SITE_DIR, html=True), name="site")
