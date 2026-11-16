"""Laws.

United States: federal laws, bills and Federal Register documents are US government works and in the
public domain.
- Federal Register API (no key): new rules and proposed rules.
- Congress.gov API (free key from api.data.gov, set CONGRESS_API_KEY): bills and their status.

India: official texts are on the India Code portal (indiacode.nic.in) and bill status on Parliament
sites; check their reuse terms before scraping. The prototype uses Wikipedia articles on Indian acts
(CC BY-SA), which link to the official texts.
"""
from __future__ import annotations

from ..config import get_settings
from . import SourceDoc, http_client
from .wikipedia import fetch_article

FEDERAL_REGISTER = "https://www.federalregister.gov/api/v1/documents.json"
CONGRESS = "https://api.congress.gov/v3/bill"

INDIA_LAW_ARTICLES = [
    "Bharatiya Nyaya Sanhita",
    "Bharatiya Nagarik Suraksha Sanhita",
    "Bharatiya Sakshya Adhiniyam",
    "Right to Information Act, 2005",
    "Digital Personal Data Protection Act, 2023",
    "Fundamental rights in India",
]

US_LAW_ARTICLES = [
    "CHIPS and Science Act",
    "Inflation Reduction Act",
    "First Amendment to the United States Constitution",
    "Civil Rights Act of 1964",
]


def federal_register_latest(limit: int = 5, doc_type: str = "RULE") -> list[SourceDoc]:
    params = {"per_page": limit, "order": "newest", "conditions[type][]": doc_type,
              "fields[]": ["title", "abstract", "html_url", "publication_date", "agencies", "type"]}
    with http_client() as client:
        data = client.get(FEDERAL_REGISTER, params=params).json()
    docs = []
    for item in data.get("results", []):
        agencies = ", ".join(a.get("name", "") for a in item.get("agencies", []) if a.get("name"))
        text = f"{item.get('type', '')} published by {agencies or 'a federal agency'}. {item.get('abstract') or ''}"
        docs.append(SourceDoc(url=item["html_url"], title=item["title"], kind="law", licence="Public domain",
                              publisher="Federal Register", text=text.strip(),
                              published=item.get("publication_date"), domain="laws_us",
                              meta={"status": "proposed" if doc_type == "PRORULE" else "final rule"}))
    return docs


def congress_recent_bills(limit: int = 5) -> list[SourceDoc]:
    key = get_settings().congress_api_key
    if not key:
        return []
    with http_client() as client:
        data = client.get(CONGRESS, params={"api_key": key, "format": "json", "limit": limit,
                                            "sort": "updateDate+desc"}).json()
    docs = []
    for bill in data.get("bills", []):
        action = bill.get("latestAction", {})
        label = f"{bill.get('type', '')} {bill.get('number', '')}".strip()
        text = (f"Bill {label} in the {bill.get('congress')}th Congress: {bill.get('title', '')}. "
                f"Latest action ({action.get('actionDate', 'date unknown')}): {action.get('text', 'none listed')}.")
        url = (f"https://www.congress.gov/bill/{bill.get('congress')}th-congress/"
               f"{'house' if str(bill.get('type', '')).upper().startswith('H') else 'senate'}-bill/{bill.get('number')}")
        docs.append(SourceDoc(url=url, title=f"{label}: {bill.get('title', '')}", kind="law",
                              licence="Public domain", publisher="Congress.gov", text=text,
                              published=action.get("actionDate"), domain="laws_us",
                              meta={"status": "proposed"}))
    return docs


def india_law_articles(titles: list[str] | None = None) -> list[SourceDoc]:
    docs = []
    for title in titles or INDIA_LAW_ARTICLES:
        doc = fetch_article(title, domain="laws_in")
        if doc:
            docs.append(doc)
    return docs


def us_law_articles(titles: list[str] | None = None) -> list[SourceDoc]:
    docs = []
    for title in titles or US_LAW_ARTICLES:
        doc = fetch_article(title, domain="laws_us")
        if doc:
            docs.append(doc)
    return docs
