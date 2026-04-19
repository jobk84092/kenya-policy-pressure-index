"""
GDELT Political Pressure fetcher.

Queries the GDELT Project's free Doc API for Kenya-related news events
over the past 30 days, deriving a political pressure score from two
parallel queries:

  Query A – generic conflict/unrest (broad catch-all)
  Query B – Kenya-specific political actors, parties, and security events

Score components
----------------
  • Volume  (40 %): combined article count vs calibrated baseline
  • Tone    (40 %): negativity of average GDELT article tone
  • Specificity (20 %): share of Query-B (Kenya-specific) articles vs total
                        — rewards breadth of domestic political coverage

GDELT Doc API docs: https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/
"""
from __future__ import annotations

import requests
from loguru import logger

from kppi.data.fetchers.base import BaseFetcher, IndicatorReading, _get_json

_GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"

# Query A: generic conflict / instability events in Kenya
_QUERY_A = (
    '"Kenya" (protest OR riot OR strike OR "political violence" '
    'OR demonstrations OR "government crisis" OR unrest OR clashes '
    'OR "police crackdown" OR "tear gas" OR casualties)'
)

# Query B: Kenya-specific political actors, parties, and security apparatus
_QUERY_B = (
    '"Kenya" (Ruto OR Odinga OR ODM OR Azimio OR "UDA party" '
    'OR "hustler nation" OR GSU OR "Gen Z" OR "finance bill" '
    'OR "cost of living" OR "fuel prices" OR "IEBC" '
    'OR "National Assembly" OR "Senate Kenya" OR impeachment '
    'OR "cabinet secretary" OR "court order Kenya")'
)

# Calibration baselines (articles per 30-day window)
_MAX_COMBINED_ARTICLES = 500   # ~4x calm baseline → 100 % volume score
_TONE_NEUTRAL = 0.0
_TONE_FLOOR = -10.0            # GDELT tone scale lower bound


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _query_gdelt(query: str, maxrecords: int = 250) -> list[dict]:
    """Run a single GDELT Doc API query; returns article list or [].

    Raises requests.HTTPError for 429 (rate-limit) so the caller can
    propagate the failure up through safe_fetch rather than silently
    returning a zero score.
    """
    params = {
        "query": query,
        "mode": "artlist",
        "maxrecords": str(maxrecords),
        "timespan": "30d",
        "format": "json",
        "sourcelang": "english",
    }
    try:
        data = _get_json(_GDELT_DOC_API, params=params, timeout=20)
        return data.get("articles", []) or []
    except requests.exceptions.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 429:
            raise  # let safe_fetch handle rate-limit as a real failure
        logger.warning("GDELT API error {}: treating as zero events", exc)
        return []


def _avg_tone(articles: list[dict]) -> float:
    tones = []
    for art in articles:
        try:
            tones.append(float(art.get("tone", _TONE_NEUTRAL) or _TONE_NEUTRAL))
        except (TypeError, ValueError):
            pass
    return sum(tones) / len(tones) if tones else _TONE_NEUTRAL


class PoliticalPressureFetcher(BaseFetcher):
    """
    Returns a political pressure score 0–100 based on Kenya conflict/
    protest news volume and sentiment from GDELT.

    Uses two parallel queries:
    - Query A: generic Kenya conflict/unrest (broad)
    - Query B: Kenya-specific political actors and events (targeted)

    Score = 40 % volume + 40 % sentiment + 20 % specificity
    """

    def fetch(self) -> IndicatorReading:
        arts_a = _query_gdelt(_QUERY_A, maxrecords=250)
        arts_b = _query_gdelt(_QUERY_B, maxrecords=250)

        # De-duplicate by URL so overlapping articles don't double-count
        urls_a = {a.get("url", "") for a in arts_a}
        arts_b_unique = [a for a in arts_b if a.get("url", "") not in urls_a]
        all_articles = arts_a + arts_b_unique

        total_count = len(all_articles)
        count_b = len(arts_b)  # raw B count (before dedup) for specificity

        # ── Volume score (0–100) ───────────────────────────────────────────
        volume_score = _clamp(
            (total_count / _MAX_COMBINED_ARTICLES) * 100,
            0.0, 100.0,
        )

        # ── Sentiment score (0–100) ────────────────────────────────────────
        avg_tone_val = _avg_tone(all_articles)
        sentiment_score = _clamp(
            (max(-avg_tone_val, 0) / abs(_TONE_FLOOR)) * 100,
            0.0, 100.0,
        )

        # ── Specificity score (0–100) ──────────────────────────────────────
        # High specificity = lots of Kenya political actor coverage → pressure
        specificity_score = _clamp(
            (count_b / max(total_count, 1)) * 100,
            0.0, 100.0,
        )

        # ── Combined score ─────────────────────────────────────────────────
        combined = (
            0.40 * volume_score
            + 0.40 * sentiment_score
            + 0.20 * specificity_score
        )

        logger.debug(
            "GDELT: total_articles={} (A={}, B_unique={}), avg_tone={:.2f}, "
            "volume={:.1f}, sentiment={:.1f}, specificity={:.1f} → combined={:.1f}",
            total_count, len(arts_a), len(arts_b_unique),
            avg_tone_val, volume_score, sentiment_score, specificity_score, combined,
        )

        return IndicatorReading(
            name="political_pressure",
            value=round(combined, 2),
            unit="score_0_100",
            source="GDELT Doc API v2 (dual-query)",
            notes=(
                f"{total_count} articles (general={len(arts_a)}, KE-specific={len(arts_b_unique)}); "
                f"avg tone {avg_tone_val:.2f}; "
                f"volume={volume_score:.1f}, sentiment={sentiment_score:.1f}, "
                f"specificity={specificity_score:.1f}"
            ),
        )
