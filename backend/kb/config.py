"""Settings read from environment variables (or a .env file in backend/)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    env_file = BACKEND_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

# Feeds from US government publishers are public domain, so their text can be summarised freely.
# Add other outlets as "Link only": the app keeps just their headline, short summary and link.
DEFAULT_NEWS_FEEDS = [
    {"url": "https://www.nasa.gov/news-release/feed/", "publisher": "NASA", "licence": "Public domain",
     "domain": "science"},
    {"url": "https://www.federalreserve.gov/feeds/press_monetary.xml", "publisher": "Federal Reserve",
     "licence": "Public domain", "domain": "economics"},
]


@dataclass
class Settings:
    db_path: Path = field(default_factory=lambda: Path(os.getenv("KB_DB_PATH", BACKEND_DIR / "data" / "kb.sqlite3")))
    llm_api_key: str | None = field(default_factory=lambda: os.getenv("LLM_API_KEY"))
    # Model ids come from settings (.env locally, repository secrets in the cloud), not from code.
    draft_model: str = field(default_factory=lambda: os.getenv("LLM_DRAFT_MODEL", ""))
    verify_model: str = field(default_factory=lambda: os.getenv("LLM_VERIFY_MODEL", ""))
    congress_api_key: str | None = field(default_factory=lambda: os.getenv("CONGRESS_API_KEY"))
    user_agent: str = field(default_factory=lambda: os.getenv(
        "KB_USER_AGENT", "ai-knowledge-app-prototype/0.1 (contact: set KB_USER_AGENT in .env)"))
    # A card is published only if at least this share of its claims are supported by its sources.
    min_quality: float = field(default_factory=lambda: float(os.getenv("KB_MIN_QUALITY", "0.8")))
    # Cosine similarity above which two news cards are treated as the same story.
    story_threshold: float = field(default_factory=lambda: float(os.getenv("KB_STORY_THRESHOLD", "0.30")))

    @property
    def use_fake_llm(self) -> bool:
        return os.getenv("KB_FAKE_LLM", "").lower() in {"1", "true", "yes"} or not self.llm_api_key


def get_settings() -> Settings:
    return Settings()
