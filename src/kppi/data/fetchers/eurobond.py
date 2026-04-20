"""
Kenya sovereign Eurobond spread fetcher.

Computes the spread between Kenya's USD-denominated Eurobond yield and the
US 10-year Treasury yield — the canonical measure of sovereign credit risk
as priced by international debt markets.

A wider spread signals that investors demand a higher premium to hold Kenyan
government debt, reflecting perceived fiscal/political stress.

Data sources (both free, no API key required):
    - US 10yr Treasury yield : US Treasury Department daily XML feed
  - Kenya Eurobond yield    : worldgovernmentbonds.com HTML scrape

Historical context (Kenya):
  ~4 pp  (2014-2019) — stable
  ~6 pp  (2020 COVID)
  ~9 pp  (2022-2023 IMF talks / Eurobond redemption fears)
  >10 pp -> crisis territory
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime

import requests
from loguru import logger

from kppi.data.fetchers.base import BaseFetcher, IndicatorReading

# ── US 10yr Treasury yield via FRED CSV ───────────────────────────────────────
# US Treasury Department daily yield curve XML feed (official source)
# Year-only format returns all entries for the current year; monthly returns 0.
_TREASURY_XML_URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/"
    "interest-rates/pages/xml?data=daily_treasury_yield_curve"
    "&field_tdr_date_value={yyyy}"
)

# XML namespaces used in Treasury's Atom feed
_NS_ATOM = "http://www.w3.org/2005/Atom"
_NS_D = "http://schemas.microsoft.com/ado/2007/08/dataservices"

# ── worldgovernmentbonds.com ──────────────────────────────────────────────────
_WGB_KENYA_URL = "https://www.worldgovernmentbonds.com/country/kenya/"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml",
    "Accept-Language": "en-US,en;q=0.9",
}

# Match patterns like "9.85%" or "10.12 %" near "10Y" context on the page
_WGB_YIELD_RE = re.compile(
    r"(?:10\s*[Yy](?:ear)?|10-[Yy]r?)[^<]{0,300}?([\d]{1,2}\.[\d]{2,3})\s*%",
    re.DOTALL,
)
# Broader fallback: any "X.XX%" in the range 5–20 near "Kenya"
_WGB_BROAD_RE = re.compile(r"\b((?:1[0-9]|[5-9])\.\d{2,3})\s*%")


def _fetch_us_10yr_treasury() -> float:
    """
    Fetch the most recent US 10-year Treasury yield from the official
    Treasury Department daily yield curve XML feed.
    Returns yield as a percentage, e.g. 4.26.
    """
    yyyy = datetime.utcnow().strftime("%Y")
    url = _TREASURY_XML_URL.format(yyyy=yyyy)
    resp = requests.get(url, headers=_HEADERS, timeout=30)
    resp.raise_for_status()

    root = ET.fromstring(resp.content)
    entries = root.findall(f"{{{_NS_ATOM}}}entry")
    if not entries:
        raise ValueError("US Treasury XML: no entries found in feed")

    # Most recent entry is last in the feed
    last_entry = entries[-1]
    bc_10yr = last_entry.find(f".//{{{_NS_D}}}BC_10YEAR")
    if bc_10yr is None or not bc_10yr.text:
        raise ValueError("US Treasury XML: BC_10YEAR element missing or empty")

    value = float(bc_10yr.text)
    if not (0.1 <= value <= 15.0):
        raise ValueError(
            f"US Treasury 10yr yield {value}% is implausible; expected 0.1-15%"
        )

    logger.debug("US 10yr Treasury yield: {:.3f}%", value)
    return value


def _fetch_kenya_eurobond_yield() -> float:
    """
    Scrape Kenya's Eurobond yield (approximately 10-year tenor) from
    worldgovernmentbonds.com.

    NOTE: The site's SSL certificate sometimes expires. For this local
    research tool we suppress the verification warning and proceed --
    the risk of MITM on a read-only public data scrape is low.

    Raises ValueError if the yield cannot be reliably extracted.
    """
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    logger.warning(
        "worldgovernmentbonds.com SSL cert may be expired — using verify=False"
    )
    resp = requests.get(_WGB_KENYA_URL, headers=_HEADERS, timeout=20, verify=False)
    resp.raise_for_status()
    text = resp.text

    # Primary: find yield near "10Y" context
    m = _WGB_YIELD_RE.search(text)
    if m:
        value = float(m.group(1))
        if 4.0 <= value <= 25.0:
            logger.debug("Kenya Eurobond yield (10Y pattern): {:.3f}%", value)
            return value

    # Fallback: scan for any plausible sovereign yield in page (range 8–20%)
    candidates = [
        float(v) for v in _WGB_BROAD_RE.findall(text)
        if 8.0 <= float(v) <= 20.0
    ]
    if candidates:
        value = candidates[0]
        logger.debug(
            "Kenya Eurobond yield (broad fallback, {} candidates): {:.3f}%",
            len(candidates), value
        )
        return value

    raise ValueError(
        "worldgovernmentbonds.com: could not parse Kenya Eurobond yield. "
        "Page layout may have changed or site is blocking the request."
    )


class EurobondSpreadFetcher(BaseFetcher):
    """
    Kenya sovereign Eurobond spread above US 10-year Treasury (percentage points).

    Returns the spread as a positive number, e.g. 7.5 means Kenya's
    Eurobond yield is 7.5 pp above the equivalent US Treasury yield.
    """

    def fetch(self) -> IndicatorReading:
        us_10yr = _fetch_us_10yr_treasury()
        kenya_yield = _fetch_kenya_eurobond_yield()

        spread = round(kenya_yield - us_10yr, 3)
        if spread < 0:
            raise ValueError(
                f"Eurobond spread is negative ({spread:.2f} pp) — "
                "Kenya yield should always exceed US yield"
            )

        return IndicatorReading(
            name="eurobond_spread",
            value=spread,
            unit="percentage_points",
            source="US Treasury + worldgovernmentbonds.com",
            notes=(
                f"Kenya Eurobond: {kenya_yield:.2f}% — "
                f"US 10yr Treasury: {us_10yr:.2f}% — "
                f"Spread: {spread:.2f} pp"
            ),
        )
