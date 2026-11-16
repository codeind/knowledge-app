"""LLM calls: draft cards from source passages, then verify each claim against those passages.

Both calls use a forced tool call so the model returns JSON that matches a fixed schema.
With no LLM_API_KEY (or KB_FAKE_LLM=1) a simple offline writer is used, so the pipeline,
tests and demo still run; its cards are extractive and marked unverified.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Protocol

from .config import Settings, get_settings

CARD_TYPES = ["news", "concept", "event", "profile", "law", "lesson", "viewpoint"]
LABELS = ["Fact", "Interpretation", "Opinion", "Disputed"]

SAVE_CARDS_TOOL = {
    "name": "save_cards",
    "description": "Save the knowledge cards written from the passages.",
    "input_schema": {
        "type": "object",
        "properties": {
            "cards": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Under 80 characters, specific."},
                        "body": {"type": "string", "description": "40-90 words, plain language, own words."},
                        "card_type": {"type": "string", "enum": CARD_TYPES},
                        "label": {"type": "string", "enum": LABELS},
                        "viewpoint": {"type": "string",
                                      "description": "Only for viewpoint cards: whose view this presents."},
                        "event_date": {"type": "string", "description": "ISO date (YYYY-MM-DD) if the card is "
                                       "about a dated event and the passages state the date; else empty."},
                        "claims": {
                            "type": "array",
                            "description": "Every factual statement in the body, each with the passage ids "
                                           "that support it.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "text": {"type": "string"},
                                    "passage_ids": {"type": "array", "items": {"type": "integer"}},
                                },
                                "required": ["text", "passage_ids"],
                            },
                        },
                        "entities": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "kind": {"type": "string", "enum": [
                                        "organisation", "person", "place", "object", "law", "event", "other"]},
                                },
                                "required": ["name", "kind"],
                            },
                        },
                        "tags": {"type": "array", "items": {"type": "string"},
                                 "description": "3-6 lowercase topic tags, e.g. 'rockets', 'interest rates'."},
                    },
                    "required": ["title", "body", "card_type", "label", "claims", "entities", "tags"],
                },
            }
        },
        "required": ["cards"],
    },
}

VERIFY_TOOL = {
    "name": "record_verdicts",
    "description": "Record whether each claim is supported by the passages.",
    "input_schema": {
        "type": "object",
        "properties": {
            "verdicts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "claim_index": {"type": "integer"},
                        "verdict": {"type": "string", "enum": ["supported", "partial", "unsupported"]},
                        "reason": {"type": "string"},
                    },
                    "required": ["claim_index", "verdict"],
                },
            }
        },
        "required": ["verdicts"],
    },
}

DRAFT_SYSTEM = """You write short knowledge cards for a learning app read by general adult readers.
Rules:
- Use ONLY the numbered passages given. Never add facts from memory. If the passages do not support
  something, leave it out.
- Write in your own words. Quote at most 12 words from any passage, in quotation marks.
- List every factual statement in the body as a claim, with the ids of the passages that support it.
- Label each card: Fact (directly stated in sources), Interpretation (explains or connects facts),
  Opinion (a named person's or group's view; name them), Disputed (sources disagree).
- Political, economic or ideological debates: never take a side. Describe each side the way its own
  supporters would recognise as fair, as separate viewpoint cards, and say whose view it is.
- Laws: say what the law or bill does in plain words, its status (proposed, passed, in force), and
  never give legal advice.
- Prefer fewer, better cards over many thin ones."""

VERIFY_SYSTEM = """You check knowledge cards against their source passages. For each numbered claim decide:
supported (the passages state it), partial (partly stated, or stated less precisely), or
unsupported (not in the passages, or contradicted). Judge only against the passages, not your own
knowledge. Be strict about numbers, dates and names."""


@dataclass
class Passage:
    id: int
    source_title: str
    text: str


class LLM(Protocol):
    def draft_cards(self, passages: list[Passage], *, section: str, domain: str, guidance: str,
                    max_cards: int) -> list[dict[str, Any]]: ...

    def verify(self, card: dict[str, Any], passages: list[Passage]) -> list[str]: ...


def _format_passages(passages: list[Passage]) -> str:
    return "\n\n".join(f"[{p.id}] (from: {p.source_title})\n{p.text}" for p in passages)


class LLMClient:
    def __init__(self, settings: Settings | None = None):
        import anthropic  # imported here so the offline mode needs no SDK

        self.settings = settings or get_settings()
        if not (self.settings.draft_model and self.settings.verify_model):
            raise RuntimeError("Set LLM_DRAFT_MODEL and LLM_VERIFY_MODEL (model ids from your LLM provider).")
        self.client = anthropic.Anthropic(api_key=self.settings.llm_api_key)

    def _tool_call(self, *, model: str, system: str, prompt: str, tool: dict, max_tokens: int) -> dict:
        resp = self.client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            tools=[tool],
            tool_choice={"type": "tool", "name": tool["name"]},
            messages=[{"role": "user", "content": prompt}],
        )
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use":
                return block.input  # type: ignore[return-value]
        raise RuntimeError("Model returned no tool call")

    def draft_cards(self, passages, *, section, domain, guidance, max_cards):
        prompt = (
            f"Section: {section}\nDomain: {domain}\nWrite up to {max_cards} cards.\n"
            f"Guidance: {guidance}\n\nPassages:\n{_format_passages(passages)}"
        )
        out = self._tool_call(model=self.settings.draft_model, system=DRAFT_SYSTEM, prompt=prompt,
                              tool=SAVE_CARDS_TOOL, max_tokens=4000)
        valid_ids = {p.id for p in passages}
        cards = out.get("cards", [])[:max_cards]
        for card in cards:
            for claim in card.get("claims", []):
                claim["passage_ids"] = [i for i in claim.get("passage_ids", []) if i in valid_ids]
        return cards

    def verify(self, card, passages):
        claims = "\n".join(f"{i}. {c['text']}" for i, c in enumerate(card.get("claims", [])))
        prompt = (f"Card title: {card['title']}\nCard body: {card['body']}\n\nClaims:\n{claims}\n\n"
                  f"Passages:\n{_format_passages(passages)}")
        out = self._tool_call(model=self.settings.verify_model, system=VERIFY_SYSTEM, prompt=prompt,
                              tool=VERIFY_TOOL, max_tokens=2000)
        verdicts = ["unsupported"] * len(card.get("claims", []))
        for v in out.get("verdicts", []):
            idx = v.get("claim_index")
            if isinstance(idx, int) and 0 <= idx < len(verdicts):
                verdicts[idx] = v.get("verdict", "unsupported")
        return verdicts


_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_STOP = set("the a an and or of to in on for with by from at as is was were be been are this that these those "
            "it its into than then their there which who whom whose has have had not but also more most".split())


class FakeLLM:
    """Offline stand-in: builds one extractive card per source. Good for demos and tests, not for users."""

    def draft_cards(self, passages, *, section, domain, guidance, max_cards):
        by_source: dict[str, list[Passage]] = {}
        for p in passages:
            by_source.setdefault(p.source_title, []).append(p)
        cards = []
        for title, ps in list(by_source.items())[:max_cards]:
            sentences = [s for s in _SENTENCE.split(" ".join(p.text for p in ps[:2])) if len(s.split()) > 4][:3]
            if not sentences:
                continue
            words = [w.lower().strip(".,;:()\"'") for w in " ".join(sentences).split()]
            tags = [w for w in dict.fromkeys(words) if len(w) > 5 and w not in _STOP][:4]
            cards.append({
                "title": title[:80],
                "body": " ".join(sentences),
                "card_type": "news" if section == "news" else "concept",
                "label": "Fact",
                "claims": [{"text": s, "passage_ids": [ps[0].id]} for s in sentences],
                "entities": [{"name": title.split(":")[0][:60], "kind": "other"}],
                "tags": tags or [domain],
            })
        return cards

    def verify(self, card, passages):
        corpus = " ".join(p.text for p in passages)
        return ["supported" if c["text"] in corpus else "partial" for c in card.get("claims", [])]


def get_llm(settings: Settings | None = None) -> LLM:
    settings = settings or get_settings()
    return FakeLLM() if settings.use_fake_llm else LLMClient(settings)


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)
