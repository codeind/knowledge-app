"""Command line for the pipeline.

    python -m kb.cli init                     create the database
    python -m kb.cli seed                     load the sample cards (no API key needed)
    python -m kb.cli run all                  run every job, then rebuild links
    python -m kb.cli run daily                news + new US rules, then relink (what the schedule runs)
    python -m kb.cli run news                 news feeds
    python -m kb.cli run learn --domain economics [--titles "Inflation" "Supply and demand"]
    python -m kb.cli run laws --country us|in
    python -m kb.cli run books [--topics rockets inflation] [--excerpt]
    python -m kb.cli link                     rebuild Go deeper links
    python -m kb.cli stats                    quality numbers
"""
from __future__ import annotations

import argparse
import json
import logging

from . import db
from .config import get_settings
from .linking import rebuild_links
from .llm import get_llm
from . import pipeline
from .seed import load_seed


def stats(conn) -> dict:
    by_status = {r["status"]: r["n"] for r in conn.execute("SELECT status, COUNT(*) n FROM cards GROUP BY status")}
    by_domain = {f"{r['section']}:{r['domain']}": r["n"] for r in conn.execute(
        "SELECT section, domain, COUNT(*) n FROM cards WHERE status='published' GROUP BY section, domain")}
    verdicts = {r["verdict"]: r["n"] for r in conn.execute(
        "SELECT verdict, COUNT(*) n FROM card_claims GROUP BY verdict")}
    checked = sum(v for k, v in verdicts.items() if k != "unchecked")
    return {
        "cards_by_status": by_status,
        "published_by_domain": by_domain,
        "claim_verdicts": verdicts,
        "claim_support_rate": round(verdicts.get("supported", 0) / checked, 3) if checked else None,
        "stories": conn.execute("SELECT COUNT(*) FROM stories").fetchone()[0],
        "links": conn.execute("SELECT COUNT(*) FROM card_links").fetchone()[0],
        "books": conn.execute("SELECT COUNT(*) FROM books").fetchone()[0],
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="kb")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    sub.add_parser("seed")
    sub.add_parser("link")
    sub.add_parser("stats")
    run = sub.add_parser("run")
    run.add_argument("job", choices=["all", "daily", "news", "learn", "laws", "books"])
    run.add_argument("--domain", choices=list(pipeline.LEARN_TOPICS))
    run.add_argument("--titles", nargs="*")
    run.add_argument("--country", choices=["us", "in"])
    run.add_argument("--topics", nargs="*")
    run.add_argument("--excerpt", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    conn = db.connect()
    db.init_db(conn)

    if args.cmd == "init":
        print(f"Database ready at {get_settings().db_path}")
        return
    if args.cmd == "seed":
        print(json.dumps(load_seed(conn), indent=2))
        print(json.dumps(rebuild_links(conn), indent=2))
        return
    if args.cmd == "link":
        print(json.dumps(rebuild_links(conn), indent=2))
        return
    if args.cmd == "stats":
        print(json.dumps(stats(conn), indent=2))
        return

    settings = get_settings()
    if settings.use_fake_llm:
        print("No LLM_API_KEY set (or KB_FAKE_LLM=1): using the offline writer. Cards will be extractive.")
    llm = get_llm(settings)
    if args.job == "all":
        result = pipeline.run_all(conn, llm)
    elif args.job == "daily":
        result = pipeline.job_daily(conn, llm)
    elif args.job == "news":
        result = dict(pipeline.job_news(conn, llm))
    elif args.job == "learn":
        if not args.domain:
            parser.error("run learn needs --domain")
        result = dict(pipeline.job_learn(conn, llm, args.domain, args.titles))
    elif args.job == "laws":
        if not args.country:
            parser.error("run laws needs --country us|in")
        result = dict(pipeline.job_laws(conn, llm, args.country))
    else:
        result = dict(pipeline.job_books(conn, llm, args.topics, args.excerpt))
    if args.job not in {"all", "daily"}:
        result["links"] = rebuild_links(conn)
    print(json.dumps(result, indent=2, default=str))

    # Fail the run (so the scheduler reports it) when sources errored and nothing was drafted.
    parts = [v for v in result.values() if isinstance(v, dict)] if args.job in {"all", "daily"} else [result]
    errors = sum(p.get("errors", 0) for p in parts)
    drafted = sum(p.get("drafted", 0) for p in parts)
    if errors and not drafted:
        raise SystemExit(f"Content job failed: {errors} source errors and no cards drafted.")


if __name__ == "__main__":
    main()
