"""
Kenya official foreign exchange reserves fetcher.

Sources tried in order:
  1. CBK MPC press releases (WordPress posts) -- real-time, when parseable
  2. World Bank API (FI.RES.TOTL.CD / BM.GSR.GNFS.CD) -- annual, ~1yr lag, 60s timeout

Returns months of import cover -- the IMF standard reserve adequacy metric.
IMF guideline: >= 3 months minimum; >= 4 months adequate for Kenya.

No mock fallback. If all sources fail, the fetcher raises and the pipeline
returns None, letting the calculator substitute a neutral 50.
"""
from __future__ import annotations

import re

import requests
from loguru import logger

from kppi.data.fetchers.base import BaseFetcher, IndicatorReading

# ─── CBK MPC scraper ─────────────────────────────────────────────────────────
_CBK_WP_POSTS_URL = "https://www.centralbank.go.ke/wp-json/wp/v2/posts"
_CBK_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml",
}
_MONTHS_RE = re.compile(
    r"([\d]+\.[\d]{1,3})\s*months?\s*(?:of\s*import(?:\s*cover)?)?",
    re.IGNORECASE,
)

# ─── World Bank API ───────────────────────────────────────────────────────────
_WB_BASE = "https://api.worldbank.org/v2/country/KE/indicator"
INDICATOR_RESERVES_USD = "FI.RES.TOTL.CD"   # Total reserves incl. gold, current USD
INDICATOR_IMPORTS_USD  = "BM.GSR.GNFS.CD"   # Imports goods+services, current USD
_WB_TIMEOUT = 60  # seconds -- World Bank CDN can be slow; 60s is reliable


def _wb_value(indicator: str, timeout: int = _WB_TIMEOUT) -> float:
    """Return the most recent non-null World Bank annual observation for Kenya."""
    url = f"{_WB_BASE}/{indicator}"
    r = requests.get(url, params={"format": "json", "per_page": 5}, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list) or len(data) < 2 or not data[1]:
        raise ValueError(f"Empty World Bank response for {indicator}")
    for obs in data[1]:
        if obs.get("value") is not None:
            return float(obs["value"])
    raise ValueError(f"All World Bank observations null for {indicator}")


class ForexReservesFetcher(BaseFetcher):
    """
    Kenya forex reserves in months of import cover.

    Scrapes the latest CBK MPC press-release post for a sentence like
    "usable foreign exchange reserves stood at ... (Y.Y months of import cover)".
    """

    def fetch(self) -> IndicatorReading:
        resp = requests.get(
            _CBK_WP_POSTS_URL,
            params={"search": "monetary policy", "per_page": 5, "_fields": "link,title"},
            headers=_CBK_HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        posts = resp.json()
        if not posts:
            raise ValueError("CBK WP API returned no MPC posts")

        for post in posts:
            post_url = post.get("link", "")
            if not post_url:
                continue
            try:
                page = requests.get(post_url, headers=_CBK_HEADERS, timeout=15)
                page.raise_for_status()
                text = re.sub(r"<[^>]+>", " ", page.text)
                text = re.sub(r"\s+", " ", text)
                m = _MONTHS_RE.search(text)
                if m:
                    value = float(m.group(1))
                    if 1.0 <= value <= 24.0:
                        logger.debug("CBK MPC: {:.2f} months from {}", value, post_url)
                        return IndicatorReading(
                            name="forex_reserves",
                            value=value,
                            unit="months_import_cover",
                            source="CBK - MPC press release",
                            notes=f"Forex reserves: {value:.2f} months of import cover",
                        )
            except Exception as e:
                logger.debug("CBK MPC post failed for {}: {}", post_url, e)
                continue

        raise ValueError("CBK MPC posts: could not parse months of import cover")


class WorldBankReservesFetcher(BaseFetcher):
    """
    Fallback: World Bank computed months of import cover for Kenya.

    Divides total reserves in USD (FI.RES.TOTL.CD) by monthly imports
    (BM.GSR.GNFS.CD / 12). Annual data with ~12-month lag; timeout is
    60s because the World Bank API CDN can be slow.
    """

    def fetch(self) -> IndicatorReading:
        res_usd = _wb_value(INDICATOR_RESERVES_USD)
        imp_usd = _wb_value(INDICATOR_IMPORTS_USD)
        if imp_usd <= 0:
            raise ValueError("World Bank imports value is zero/negative")
        monthly_imp = imp_usd / 12
        months = res_usd / monthly_imp
        if not (1.0 <= months <= 24.0):
            raise ValueError(f"World Bank computed months {months:.2f} is implausible")
        logger.debug(
            "WB reserves: USD {:.2f}bn / USD {:.2f}bn/mo = {:.2f} months",
            res_usd / 1e9, monthly_imp / 1e9, months,
        )
        return IndicatorReading(
            name="forex_reserves",
            value=round(months, 2),
            unit="months_import_cover",
            source="World Bank - FI.RES.TOTL.CD / BM.GSR.GNFS.CD (lagged ~1yr)",
            notes=(
                f"Total reserves USD {res_usd/1e9:.1f}bn / monthly imports "
                f"USD {monthly_imp/1e9:.2f}bn = {months:.2f} months"
            ),
        )
