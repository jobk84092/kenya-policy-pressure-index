"""
Kenya political pressure fetcher from Google News RSS.

No API key required. Uses Kenya-focused RSS searches and converts
recent article volume + severity keywords into a 0-100 pressure score.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Iterable
from urllib.parse import urlencode
import xml.etree.ElementTree as ET

import requests

from kppi.data.fetchers.base import BaseFetcher, IndicatorReading

_GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"

_QUERY_A = (
    'Kenya (protest OR riot OR clashes OR violence OR unrest '
    'OR strike OR demonstrations OR police OR fatalities)'
)
_QUERY_B = (
    'Kenya (Ruto OR Odinga OR ODM OR Azimio OR UDA OR parliament '
    'OR senate OR IEBC OR impeachment OR "finance bill")'
)

_VOLUME_HALF_SAT = 240.0

_KEYWORD_WEIGHTS = {
    "fatal": 2.2,
    "killed": 2.2,
    "deaths": 2.2,
    "violence": 1.8,
    "clashes": 1.8,
    "riot": 1.7,
    "unrest": 1.6,
    "protest": 1.4,
    "strike": 1.2,
    "police": 1.2,
    "teargas": 1.1,
    "impeachment": 1.0,
}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _saturating_scale(value: float, half_saturation: float) -> float:
    """Map unbounded counts to 0-100 with diminishing returns."""
    if half_saturation <= 0:
        return 0.0
    return _clamp((100.0 * value) / (value + half_saturation), 0.0, 100.0)


def _rss_url(query: str) -> str:
    params = {
        "q": query,
        "hl": "en-KE",
        "gl": "KE",
        "ceid": "KE:en",
    }
    return f"{_GOOGLE_NEWS_RSS}?{urlencode(params)}"


def _fetch_articles(query: str, timeout: int = 20) -> list[dict]:
    headers = {
        "User-Agent": "KPPI-Index/2.0 (research; +github.com/kppi)",
        "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
    }
    resp = requests.get(_rss_url(query), headers=headers, timeout=timeout)
    resp.raise_for_status()

    root = ET.fromstring(resp.content)
    items = root.findall("./channel/item")

    articles = []
    for item in items:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        description = (item.findtext("description") or "").strip()

        published_at = None
        if pub_date:
            try:
                published_at = parsedate_to_datetime(pub_date)
                if published_at.tzinfo is not None:
                    published_at = published_at.astimezone().replace(tzinfo=None)
            except Exception:
                published_at = None

        if title and link:
            articles.append(
                {
                    "title": title,
                    "link": link,
                    "description": description,
                    "published_at": published_at,
                }
            )
    return articles


def _keyword_severity(texts: Iterable[str]) -> float:
    """Article-level severity: average weighted keyword hits per article."""
    total = 0.0
    for text in texts:
        lower = text.lower()
        article_score = 0.0
        for keyword, weight in _KEYWORD_WEIGHTS.items():
            if keyword in lower:
                article_score += weight
        total += article_score
    return total


class KenyaNewsPoliticalFetcher(BaseFetcher):
    """Kenya-specific political pressure from Google News RSS."""

    def fetch(self) -> IndicatorReading:
        arts_a = _fetch_articles(_QUERY_A)
        arts_b = _fetch_articles(_QUERY_B)

        by_link = {a["link"]: a for a in arts_a}
        for article in arts_b:
            by_link.setdefault(article["link"], article)
        articles = list(by_link.values())

        total_count = len(articles)
        recent_cutoff = datetime.utcnow() - timedelta(days=7)
        recent_count = sum(
            1
            for a in articles
            if a.get("published_at") is not None and a["published_at"] >= recent_cutoff
        )

        volume_score = _saturating_scale(total_count, _VOLUME_HALF_SAT)
        recency_score = _clamp((recent_count / max(total_count, 1)) * 100, 0.0, 100.0)
        severity_raw = _keyword_severity(
            f"{a.get('title', '')} {a.get('description', '')}" for a in articles
        )
        # Average keyword intensity per article; 12x scales typical ranges into 0-100.
        severity_score = _clamp((severity_raw / max(total_count, 1)) * 12, 0.0, 100.0)

        combined = 0.40 * volume_score + 0.40 * severity_score + 0.20 * recency_score

        return IndicatorReading(
            name="political_pressure",
            value=round(combined, 2),
            unit="score_0_100",
            source="Google News RSS (Kenya)",
            notes=(
                f"articles={total_count}, recent_7d={recent_count}, "
                f"volume={volume_score:.1f}, severity={severity_score:.1f}, recency={recency_score:.1f}"
            ),
        )
