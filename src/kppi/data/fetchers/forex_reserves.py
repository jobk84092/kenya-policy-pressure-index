"""
Kenya official foreign exchange reserves fetcher.

Primary source: Central Bank of Kenya forex reserves page (weekly, no key).
Fallback: World Bank indicator FI.RES.XGSD.ZS (total reserves in months of
imports — updated annually with a lag).

Returns months of import cover — the IMF standard reserve adequacy metric.
IMF guideline: ≥3 months is minimum; ≥4 months considered adequate for Kenya.
"""
from __future__ import annotations

import re
from typing import Any

import requests
from loguru import logger

from kppi.data.fetchers.base import BaseFetcher, IndicatorReading, _get_json

_CBK_FOREX_URL = "https://www.centralbank.go.ke/forex-reserves/"
_CBK_HEADERS = {
    "User-Agent": (
        "KPPI/2.0 research-tool "
        "(Kenya Policy Pressure Index - academic/non-commercial)"
    ),
    "Accept": "text/html,application/xhtml+xml",
}

# Matches "4.97 months" or "4.97 months of import cover" on the CBK page.
# The CBK page typically shows this near "Usable Foreign Exchange Reserves".
_MONTHS_RE = re.compile(
    r"([\d]+\.[\d]{1,3})\s*months?\s*(?:of\s*(?:import\s*cover)?)?",
    re.IGNORECASE,
)

# Matches USD value like "7,234.2" or "7234.2" (USD millions)
_USD_MILLIONS_RE = re.compile(
    r"(?:usable|official|total)\s+(?:foreign\s+exchange\s+)?reserves?\D{0,30}"
    r"(?:USD\s*)?(?:Kshs\.?\s*)?([0-9,]+\.?[0-9]*)\s*(?:million|mn|mln)?",
    re.IGNORECASE,
)

_WB_BASE = "https://api.worldbank.org/v2/country/KE/indicator"
INDICATOR_RESERVES_MONTHS = "FI.RES.XGSD.ZS"   # total reserves in months of imports


def _parse_wb_reserves(data: list[Any]) -> float:
    if len(data) < 2 or not data[1]:
        raise ValueError("Empty World Bank response for reserves indicator")
    for obs in data[1]:
        if obs.get("value") is not None:
            return float(obs["value"])
    raise ValueError("All World Bank reserve observations are null")


class ForexReservesFetcher(BaseFetcher):
    """
    Kenya official forex reserves in months of import cover (CBK primary).

    The CBK updates this weekly after the Thursday MPC briefings and
    publishes it prominently on their forex reserves page.
    """

    def fetch(self) -> IndicatorReading:
        response = requests.get(_CBK_FOREX_URL, headers=_CBK_HEADERS, timeout=20)
        response.raise_for_status()
        response.encoding = "utf-8"
        text = response.text

        # Primary: look for "X.XX months" pattern
        m = _MONTHS_RE.search(text)
        if m:
            value = float(m.group(1))
            if 1.0 <= value <= 24.0:
                return IndicatorReading(
                    name="forex_reserves",
                    value=value,
                    unit="months_import_cover",
                    source="CBK - official forex reserves",
                    notes=f"Official usable forex reserves: {value:.2f} months of import cover",
                )
            logger.warning(
                "CBK forex: parsed months value {} is implausible, ignoring", value
            )

        raise ValueError(
            "CBK forex reserves page: could not parse months of import cover. "
            "Page layout may have changed."
        )


class WorldBankReservesFetcher(BaseFetcher):
    """
    Fallback: World Bank total reserves in months of imports for Kenya.
    Typically updated with a 12+ month lag — use only when CBK scrape fails.
    """

    def fetch(self) -> IndicatorReading:
        url = f"{_WB_BASE}/{INDICATOR_RESERVES_MONTHS}"
        params = {"format": "json", "mrv": 5, "per_page": 5}
        data = _get_json(url, params=params)
        value = _parse_wb_reserves(data)
        return IndicatorReading(
            name="forex_reserves",
            value=value,
            unit="months_import_cover",
            source="World Bank - FI.RES.XGSD.ZS (lagged)",
            notes=(
                f"Total reserves in months of imports: {value:.2f} "
                "(World Bank — may lag 12+ months)"
            ),
        )
