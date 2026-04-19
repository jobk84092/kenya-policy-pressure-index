"""
World Bank Open Data fetcher + CBK direct fetcher.

World Bank retrieves Kenya macroeconomic indicators using the free,
unauthenticated World Bank Indicators REST API (v2).

CBKTBillFetcher scrapes the Central Bank of Kenya treasury-bills page
for the most recent 91-day weighted average rate – used as the primary
bond-yield source because the World Bank indicator FR.INR.TBIL is
updated with a significant lag.

Docs: https://datahelpdesk.worldbank.org/knowledgebase/articles/889392
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import requests
from loguru import logger

from kppi.data.fetchers.base import BaseFetcher, IndicatorReading, _get_json

_WB_BASE = "https://api.worldbank.org/v2/country/KE/indicator"

# World Bank indicator codes
INDICATOR_INFLATION = "FP.CPI.TOTL.ZG"     # CPI inflation (annual %)
INDICATOR_BOND_YIELD = "FR.INR.LEND"        # Lending interest rate (proxy for risk rate)
INDICATOR_T_BILL = "FR.INR.TBIL"            # Treasury bill rate (%)

_CBK_TBILL_URL = "https://www.centralbank.go.ke/bills-bonds/treasury-bills/"
_CBK_HEADERS = {
    "User-Agent": (
        "KPPI/2.0 research-tool "
        "(Kenya Policy Pressure Index - academic/non-commercial)"
    ),
    "Accept": "text/html,application/xhtml+xml",
}

# Matches "Previous Average Interest Rate: 7.4241%" on the CBK page
# (first occurrence = 91-day tenor in the "Treasury Bills on Offer" section)
_CBK_RATE_RE = re.compile(
    r"Previous\s+Average\s+Interest\s+Rate\s*:\s*([\d]+\.[\d]+)\s*%",
    re.IGNORECASE,
)


def _parse_wb_response(data: list[Any], indicator_code: str) -> float:
    """
    World Bank returns: [metadata_dict, [{"value": ..., "date": ...}, ...]].
    We take the most recent non-null observation.
    """
    if len(data) < 2 or not data[1]:
        raise ValueError(f"Empty World Bank response for {indicator_code}")

    for obs in data[1]:
        if obs.get("value") is not None:
            return float(obs["value"])

    raise ValueError(f"All observations are null for indicator {indicator_code}")


class InflationFetcher(BaseFetcher):
    """Annual CPI inflation rate for Kenya (World Bank)."""

    def fetch(self) -> IndicatorReading:
        url = f"{_WB_BASE}/{INDICATOR_INFLATION}"
        params = {"format": "json", "mrv": 5, "per_page": 5}
        data = _get_json(url, params=params)
        value = _parse_wb_response(data, INDICATOR_INFLATION)
        return IndicatorReading(
            name="inflation",
            value=value,
            unit="percent_yoy",
            source="World Bank - FP.CPI.TOTL.ZG",
            notes="Annual CPI inflation % (most recent available year)",
        )


class CBKTBillFetcher(BaseFetcher):
    """
    Kenya 91-day T-bill weighted average rate scraped directly from the
    Central Bank of Kenya treasury-bills page.

    The CBK page is updated weekly after each auction and always shows
    the most-recent 'Previous Average Interest Rate' for each tenor.
    The first rate on the page corresponds to the 91-day bill.
    """

    def fetch(self) -> IndicatorReading:
        response = requests.get(_CBK_TBILL_URL, headers=_CBK_HEADERS, timeout=15)
        response.raise_for_status()
        response.encoding = "utf-8"

        m = _CBK_RATE_RE.search(response.text)
        if not m:
            raise ValueError(
                "CBK T-bill page: could not find 'Previous Average Interest Rate' pattern. "
                "Page layout may have changed."
            )

        value = float(m.group(1))
        return IndicatorReading(
            name="bond_yield",
            value=value,
            unit="percent",
            source="CBK - 91-day T-bill weighted average rate",
            notes="Most recent 91-day treasury bill auction weighted average rate (CBK)",
        )


class TBillRateFetcher(BaseFetcher):
    """Kenya Treasury bill rate as a bond-yield proxy (World Bank).

    Note: this indicator (FR.INR.TBIL) is updated with a multi-year lag by
    the World Bank; prefer CBKTBillFetcher for current data.
    """

    def fetch(self) -> IndicatorReading:
        url = f"{_WB_BASE}/{INDICATOR_T_BILL}"
        params = {"format": "json", "mrv": 5, "per_page": 5}
        data = _get_json(url, params=params)
        value = _parse_wb_response(data, INDICATOR_T_BILL)
        return IndicatorReading(
            name="bond_yield",
            value=value,
            unit="percent",
            source="World Bank - FR.INR.TBIL",
            notes="Treasury bill rate (% pa) - proxy for government borrowing cost",
        )
