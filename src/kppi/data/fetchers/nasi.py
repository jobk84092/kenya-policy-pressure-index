"""
NASI (NSE All Share Index) fetcher – reads the index level from
nseinsider.co.ke daily market-brief post titles.

nseinsider.co.ke publishes daily "Kenyan Market Snapshot" posts whose
titles consistently embed the NASI closing value:

    "Kenyan Market Snapshot: April 17, 2026 — NASI slips 0.8% to 176.45"
    "Kenyan Market Snapshot: April 14, 2026 — NASI dips 0.4% to 178.9"

The fetcher scrapes the market-briefs category page, finds the first
(most-recent) absolute NASI value, and returns it as an IndicatorReading.

No API key is required.  nseinsider.co.ke is a third-party NSE analysis
site, not the official Nairobi Securities Exchange website.
"""
from __future__ import annotations

import re

import requests

from kppi.data.fetchers.base import BaseFetcher, IndicatorReading

_CATEGORY_URL = "https://nseinsider.co.ke/category/market-briefs"

# Matches title patterns like:
#   "NASI slips 0.8% to 176.45"
#   "NASI dips 0.4% to 178.9 amid mixed sentiment"
#   "NASI gains 1.8% to 189.23 as Banking Stocks Rally"
#   "NASI at 176.45"
_NASI_RE = re.compile(
    r"\bNASI\b\s+(?:\w+\s+[\d.]+%\s+to|at)\s+([\d]+\.[\d]+)",
    re.IGNORECASE,
)

_HEADERS = {
    "User-Agent": (
        "KPPI/2.0 research-tool "
        "(Kenya Policy Pressure Index - academic/non-commercial)"
    ),
    "Accept": "text/html,application/xhtml+xml",
}


class NASIFetcher(BaseFetcher):
    """
    Fetches the NSE All Share Index (NASI) closing level from the most
    recent daily market-brief post on nseinsider.co.ke.

    Returns an IndicatorReading with:
      name  = "market_stress"
      value = NASI index level (typical range: 120–220)
      unit  = "nasi_index_level"

    Higher NASI → stronger equity market → lower market stress.
    The normaliser inverts this: decline from baseline → higher pressure.
    """

    def fetch(self) -> IndicatorReading:
        response = requests.get(_CATEGORY_URL, headers=_HEADERS, timeout=12)
        response.raise_for_status()
        response.encoding = "utf-8"

        m = _NASI_RE.search(response.text)
        if m:
            value = float(m.group(1))
            return IndicatorReading(
                name="market_stress",
                value=value,
                unit="nasi_index_level",
                source="nseinsider.co.ke",
                notes="NSE All Share Index – higher = lower market stress",
            )

        raise ValueError(
            "No absolute NASI value found in nseinsider.co.ke market-brief titles. "
            "The most-recent post may only report a percentage change without an "
            "absolute index level.  Will fall back to mock on next retry."
        )
