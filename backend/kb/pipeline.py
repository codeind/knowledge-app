"""Content pipeline: sources -> passages -> LLM drafts cards -> second LLM call verifies claims -> publish/reject -> link.

Each job is safe to re-run: sources are upserted and cards with an existing title are skipped.
"""
from __future__ import annotations

import logging
import sqlite3
from collections import Counter
from typing import Iterable

from . import db
from .config import DEFAULT_NEWS_FEEDS, get_settings
from .linking import rebuild_links
from .llm import LLM, Passage, get_llm
from .sources import SourceDoc, chunk_text
from .sources import books as book_src
from .sources import laws as law_src
from .sources import news as news_src
from .sources import wikipedia

log = logging.getLogger("kb.pipeline")

# Starter Learn topics (Wikipedia article titles). Edit freely.
LEARN_TOPICS: dict[str, list[str]] = {
    "history": ["French Revolution", "Industrial Revolution", "Partition of India", "Fall of the Berlin Wall",
                "Space Race"],
    "ancient_history": ["Indus Valley Civilisation", "Maurya Empire", "Roman Republic", "Battle of Marathon",
                        "Ancient Egypt"],
    "economics": ["Supply and demand", "Inflation", "Monetary policy", "Comparative advantage",
                  "Keynesian economics", "Austrian school of economics"],
    "sports": ["Offside (association football)", "Powerplay (cricket)", "Expected goals",
               "Duckworth–Lewis–Stern method"],
    "science": ["Orbital speed", "Reusable launch vehicle", "SpaceX Starship"],
}

GUIDANCE = {
    "news": "Write one news card per distinct story: what happened, who, when, and why it matters. "
            "Keep to what the passages say.",
    "history": "Write event and concept cards: what happened, causes, effects. Where historians disagree, "
               "label it Disputed and say who holds which view.",
    "ancient_history": "Write event and concept cards. Separate what evidence shows from legend or later "
                       "accounts; label uncertain dates as approximate.",
    "economics": "Write concept cards that explain one idea each with a concrete example. If the passages "
                 "describe competing schools of thought, add one viewpoint card per school.",
    "sports": "Write concept cards that explain one rule, tactic or statistic each, with a simple example.",
    "laws_us": "Write law cards: what the law or rule does in plain words, when it was passed or published, "
               "and its status (proposed, passed, in force). No legal advice.",
    "laws_in": "Write law cards: what the Indian law does in plain words, when it was passed and took effect, "
               "what it replaced if anything, and its status. No legal advice.",
    "science": "Write concept cards that explain the science or engineering simply, with numbers the "
               "passages give.",
    "book": "Write idea cards: one key idea from the book per card, in your own words, naming the author.",
}


def _passages_for(conn: sqlite3.Connection, doc: SourceDoc) -> tuple[int, list[Passage]]:
    source_id = db.upsert_source(conn, url=doc.url, title=doc.title, kind=doc.kind, licence=doc.licence,
                                 publisher=doc.publisher)
    texts = book_src.excerpt_passages(doc) if doc.kind == "book" else chunk_text(doc.text)
    if doc.link_only:
        texts = texts[:1]
    ids = db.add_passages(conn, source_id, texts)
    return source_id, [Passage(id=pid, source_title=doc.title, text=t) for pid, t in zip(ids, texts)]


def process(conn: sqlite3.Connection, llm: LLM, docs: Iterable[SourceDoc], *, section: str, domain: str,
            guidance_key: str | None = None, max_cards: int = 3, job: str = "") -> Counter:
    """Draft, verify and store cards for a group of source documents (one LLM call per document)."""
    settings = get_settings()
    stats: Counter = Counter()
    run_id = conn.execute("INSERT INTO pipeline_runs (job) VALUES (?) RETURNING id",
                          (job or f"{section}:{domain}",)).fetchone()["id"]
    for doc in docs:
        source_id, passages = _passages_for(conn, doc)
        if not passages:
            continue
        guidance = GUIDANCE.get(guidance_key or domain, GUIDANCE["news"])
        if doc.link_only:
            guidance += (" This source is link-only: write at most two sentences from the headline and summary, "
                         "and do not reproduce its wording.")
        if doc.meta.get("status"):
            guidance += f" Status of this item: {doc.meta['status']}."
        try:
            drafts = llm.draft_cards(passages, section=section, domain=domain, guidance=guidance,
                                     max_cards=max_cards)
        except Exception as exc:  # keep the batch going; log and move on
            log.warning("draft failed for %s: %s", doc.url, exc)
            stats["errors"] += 1
            continue
        for draft in drafts:
            stats["drafted"] += 1
            if db.card_exists(conn, section, domain, draft["title"]):
                stats["duplicates"] += 1
                continue
            try:
                verdicts = llm.verify(draft, passages)
            except Exception as exc:
                log.warning("verify failed for %s: %s", draft["title"], exc)
                verdicts = ["unchecked"] * len(draft.get("claims", []))
            for claim, verdict in zip(draft.get("claims", []), verdicts):
                claim["verdict"] = verdict
            claims = draft.get("claims", [])
            supported = sum(1 for c in claims if c["verdict"] == "supported")
            partial = sum(1 for c in claims if c["verdict"] == "partial")
            quality = (supported + 0.5 * partial) / len(claims) if claims else 0.0
            published = quality >= settings.min_quality and not any(c["verdict"] == "unsupported" for c in claims)
            card = {
                **draft,
                "section": section,
                "domain": domain,
                "quality_score": round(quality, 3),
                "status": "published" if published else "rejected",
                # One source per card in this prototype; cross-source checks raise this to "verified".
                "verification": "single_source" if published else "unverified",
                "event_date": draft.get("event_date") or doc.published,
                "source_ids": [source_id],
            }
            db.insert_card(conn, card)
            stats["published" if published else "rejected"] += 1
        conn.commit()
    conn.execute(
        """UPDATE pipeline_runs SET finished_at = CURRENT_TIMESTAMP, cards_drafted = ?, cards_published = ?,
           cards_rejected = ?, notes = ? WHERE id = ?""",
        (stats["drafted"], stats["published"], stats["rejected"], dict(stats).__repr__(), run_id),
    )
    conn.commit()
    return stats


# ---------- jobs ----------

def job_news(conn, llm, feeds=None, per_feed: int = 5) -> Counter:
    total: Counter = Counter()
    for feed in feeds or DEFAULT_NEWS_FEEDS:
        try:
            docs = news_src.fetch_feed(feed["url"], publisher=feed["publisher"], licence=feed["licence"],
                                       domain=feed["domain"], limit=per_feed)
        except Exception as exc:
            log.warning("feed failed %s: %s", feed["url"], exc)
            total["errors"] += 1
            continue
        total += process(conn, llm, docs, section="news", domain=feed["domain"], guidance_key="news",
                         max_cards=1, job=f"news:{feed['publisher']}")
    return total


def job_learn(conn, llm, domain: str, titles: list[str] | None = None) -> Counter:
    docs = [d for d in (wikipedia.fetch_article(t, domain=domain) for t in titles or LEARN_TOPICS[domain]) if d]
    return process(conn, llm, docs, section="learn", domain=domain, max_cards=3, job=f"learn:{domain}")


def job_laws(conn, llm, country: str) -> Counter:
    if country == "us":
        docs = law_src.us_law_articles() + law_src.federal_register_latest(3) + \
            law_src.federal_register_latest(2, "PRORULE") + law_src.congress_recent_bills(3)
        return process(conn, llm, docs, section="learn", domain="laws_us", max_cards=2, job="laws:us")
    if country == "in":
        docs = law_src.india_law_articles()
        return process(conn, llm, docs, section="learn", domain="laws_in", max_cards=2, job="laws:in")
    raise ValueError("country must be 'us' or 'in'")


def job_books(conn, llm, topics: list[str] | None = None, excerpt: bool = False) -> Counter:
    """Attach books to topics: public-domain (Gutenberg) plus title-only modern books (Open Library).

    With excerpt=True, also turn part of each public-domain book into idea cards.
    """
    stats: Counter = Counter()
    if not topics:
        rows = conn.execute("SELECT tag, COUNT(*) n FROM card_tags GROUP BY tag ORDER BY n DESC LIMIT 10")
        topics = [r["tag"] for r in rows]
    for topic in topics:
        try:
            pd_books = book_src.search_public_domain(topic, limit=2)
            modern = book_src.search_modern_titles(topic, limit=2)
        except Exception as exc:
            log.warning("book search failed for %s: %s", topic, exc)
            stats["errors"] += 1
            continue
        for b in pd_books + modern:
            db.upsert_book(conn, title=b["title"], url=b["url"], public_domain=b["public_domain"],
                           author=b.get("author"), year=b.get("year"), subjects=[topic, *b.get("subjects", [])])
            stats["books"] += 1
        if excerpt:
            for b in pd_books[:1]:
                doc = book_src.fetch_book_excerpt(b)
                if doc:
                    stats += process(conn, llm, [doc], section="learn", domain="history", guidance_key="book",
                                     max_cards=2, job=f"book:{b['title'][:40]}")
    conn.commit()
    return stats


def job_daily(conn: sqlite3.Connection, llm: LLM | None = None) -> dict[str, dict]:
    """Small daily run: fresh news and newly published US rules, then relink.

    Every run adds to the archive (sources and cards are kept), so Go deeper timelines grow over time.
    """
    llm = llm or get_llm()
    results = {"news": dict(job_news(conn, llm))}
    try:
        docs = law_src.federal_register_latest(3) + law_src.federal_register_latest(2, "PRORULE")
        results["laws:us:new"] = dict(process(conn, llm, docs, section="learn", domain="laws_us", max_cards=1,
                                              job="daily:federal-register"))
    except Exception as exc:
        log.warning("federal register failed: %s", exc)
    results["links"] = rebuild_links(conn)
    return results


def run_all(conn: sqlite3.Connection, llm: LLM | None = None) -> dict[str, dict]:
    llm = llm or get_llm()
    results = {"news": dict(job_news(conn, llm))}
    for domain in LEARN_TOPICS:
        results[f"learn:{domain}"] = dict(job_learn(conn, llm, domain))
    results["laws:us"] = dict(job_laws(conn, llm, "us"))
    results["laws:in"] = dict(job_laws(conn, llm, "in"))
    results["books"] = dict(job_books(conn, llm))
    results["links"] = rebuild_links(conn)
    return results
