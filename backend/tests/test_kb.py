"""Offline tests: seed data, pipeline with the fake writer, linking and the API. No network, no API key."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from kb import api, db, pipeline
from kb.linking import go_deeper, rebuild_links
from kb.llm import FakeLLM
from kb.seed import load_seed
from kb.sources import SourceDoc, chunk_text


import os

BACKENDS = ["sqlite"] + (["postgres"] if os.getenv("TEST_DATABASE_URL") else [])


@pytest.fixture(params=BACKENDS)
def conn(request, tmp_path, monkeypatch):
    """Runs each test on SQLite, and also on Postgres when TEST_DATABASE_URL is set."""
    monkeypatch.setenv("KB_DB_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setenv("KB_FAKE_LLM", "1")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    if request.param == "postgres":
        c = db.PgConnection(os.environ["TEST_DATABASE_URL"])
        c.execute("DROP SCHEMA public CASCADE")
        c.execute("CREATE SCHEMA public")
        c.commit()
    else:
        c = db.connect(tmp_path / "test.sqlite3")
    db.init_db(c)
    yield c
    c.close()


def test_seed_is_idempotent(conn):
    first = load_seed(conn)
    second = load_seed(conn)
    assert first["cards_added"] > 40
    assert second["cards_added"] == 0


def test_go_deeper_builds_starship_timeline(conn):
    load_seed(conn)
    rebuild_links(conn)
    cid = conn.execute("SELECT id FROM cards WHERE title LIKE 'Launch tower catches%'").fetchone()["id"]
    result = go_deeper(conn, cid)
    dates = [c["event_date"] for c in result["timeline"]]
    assert dates == sorted(dates)
    assert len(result["timeline"]) >= 5
    assert any(p["title"] == "SpaceX" for p in result["players"])
    assert result["explainers"]
    assert any(b["public_domain"] for b in result["books"])
    assert result["has_depth"]


def test_manual_links_survive_rebuild(conn):
    load_seed(conn)
    before = conn.execute("SELECT COUNT(*) FROM card_links WHERE manual = 1").fetchone()[0]
    rebuild_links(conn)
    rebuild_links(conn)
    after = conn.execute("SELECT COUNT(*) FROM card_links WHERE manual = 1").fetchone()[0]
    assert before == after > 0


def test_pipeline_publishes_and_links_new_news(conn):
    load_seed(conn)
    docs = [SourceDoc(
        url="https://example.gov/starship-6", title="Starship flies again from Starbase", kind="news",
        licence="Public domain", publisher="Example agency", published="2024-11-19", domain="science",
        text=("SpaceX launched Starship from Starbase in Texas on another test flight. "
              "The Super Heavy booster returned towards the launch tower. "
              "The ship stage completed its flight and splashed down in the Indian Ocean."))]
    stats = pipeline.process(conn, FakeLLM(), docs, section="news", domain="science", max_cards=1)
    assert stats["published"] == 1
    rebuild_links(conn)
    new_id = conn.execute("SELECT id FROM cards WHERE origin = 'pipeline'").fetchone()["id"]
    card = db.get_card(conn, new_id)
    assert card["claims"] and all(c["verdict"] == "supported" for c in card["claims"])
    assert card["sources"][0]["licence"] == "Public domain"


def test_unsupported_claims_are_rejected(conn):
    class LyingLLM(FakeLLM):
        def verify(self, card, passages):
            return ["unsupported" for _ in card["claims"]]

    docs = [SourceDoc(url="https://example.org/a", title="Some article", kind="wiki", licence="CC BY-SA 4.0",
                      text="Inflation is a general rise in prices. It reduces what money can buy each year.")]
    stats = pipeline.process(conn, LyingLLM(), docs, section="learn", domain="economics", max_cards=1)
    assert stats["rejected"] == 1 and stats["published"] == 0
    assert db.query_cards(conn) == []


def test_link_only_source_keeps_one_short_passage(conn):
    long_text = " ".join(["word"] * 1000)
    doc = SourceDoc(url="https://news.example.com/x", title="Paid outlet story", kind="news",
                    licence="Link only", text=long_text)
    _, passages = pipeline._passages_for(conn, doc)
    assert len(passages) == 1


def test_chunk_text_respects_size():
    text = "\n\n".join(" ".join(["w"] * 120) for _ in range(5))
    chunks = chunk_text(text, max_words=200)
    assert all(len(c.split()) <= 240 for c in chunks)
    assert sum(len(c.split()) for c in chunks) == 600


def test_api_endpoints(conn, monkeypatch):
    load_seed(conn)
    rebuild_links(conn)
    monkeypatch.setattr(api, "_conn", conn)
    client = TestClient(api.app)

    assert client.get("/api/health").json()["published_cards"] > 40
    feed = client.get("/api/news").json()["cards"]
    dates = [c["event_date"] for c in feed]
    assert dates == sorted(dates, reverse=True)
    deep = next(c for c in feed if c["has_depth"])
    assert client.get(f"/api/cards/{deep['id']}/deeper").status_code == 200

    tracks = {t["domain"]: t["cards"] for t in client.get("/api/learn/tracks").json()["tracks"]}
    assert tracks["laws_us"] > 0 and tracks["laws_in"] > 0
    assert client.get("/api/learn/laws_in").json()["cards"]
    assert client.get("/api/learn/nope").status_code == 404

    assert client.get("/api/search", params={"q": "inflation"}).json()["cards"]
    client.post("/api/saves", json={"card_id": deep["id"]})
    assert [c["id"] for c in client.get("/api/saves").json()["cards"]] == [deep["id"]]
    client.delete(f"/api/saves/{deep['id']}")
    assert client.get("/api/saves").json()["cards"] == []
    assert "cards_by_status" in client.get("/api/stats").json()


def test_llm_client_parses_tool_calls(monkeypatch):
    """Exercise LLMClient with a stubbed API client (no network)."""
    from types import SimpleNamespace

    from kb.config import Settings
    from kb.llm import LLMClient, Passage

    calls = []

    def fake_create(**kwargs):
        calls.append(kwargs)
        if kwargs["tools"][0]["name"] == "save_cards":
            payload = {"cards": [{
                "title": "Inflation", "body": "Prices rise.", "card_type": "concept", "label": "Fact",
                "claims": [{"text": "Prices rise.", "passage_ids": [1, 999]}],
                "entities": [], "tags": ["inflation"]}]}
        else:
            payload = {"verdicts": [{"claim_index": 0, "verdict": "supported"}]}
        return SimpleNamespace(content=[SimpleNamespace(type="tool_use", input=payload)])

    settings = Settings(llm_api_key="test-key", draft_model="draft-model", verify_model="verify-model")
    llm = LLMClient(settings)
    monkeypatch.setattr(llm.client.messages, "create", fake_create)
    passages = [Passage(id=1, source_title="Wikipedia: Inflation", text="Inflation means prices rise.")]
    cards = llm.draft_cards(passages, section="learn", domain="economics", guidance="g", max_cards=2)
    assert cards[0]["claims"][0]["passage_ids"] == [1]          # unknown passage id dropped
    assert llm.verify(cards[0], passages) == ["supported"]
    assert calls[0]["tool_choice"] == {"type": "tool", "name": "save_cards"}
    assert calls[0]["model"] == settings.draft_model and calls[1]["model"] == settings.verify_model


def test_daily_job_runs_offline(conn, monkeypatch):
    load_seed(conn)
    doc = SourceDoc(url="https://example.gov/fed-new", title="Federal Reserve holds rates steady", kind="news",
                    licence="Public domain", publisher="Federal Reserve", published="2024-11-07", domain="economics",
                    text="The Federal Reserve kept its interest rate target unchanged. Officials said inflation "
                         "had eased but remained above the goal.")
    monkeypatch.setattr(pipeline.news_src, "fetch_feed", lambda *a, **k: [doc])
    monkeypatch.setattr(pipeline.law_src, "federal_register_latest", lambda *a, **k: [])
    result = pipeline.job_daily(conn, FakeLLM())
    assert result["news"]["published"] >= 1
    assert result["links"]["links"] > 0
