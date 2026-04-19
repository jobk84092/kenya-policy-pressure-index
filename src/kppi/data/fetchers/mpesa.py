"""
M-Pesa / mobile money transaction volume fetcher.

Tracks the health of Kenya's mobile money ecosystem as a proxy for
consumer economic activity. Rising volumes → healthy economy; declining
volumes → economic stress.

Primary source: Central Bank of Kenya National Payment System statistics page.
The CBK publishes monthly aggregate mobile money data (transaction count and
value) in an HTML table on their payments statistics page.

Returns the year-on-year growth rate of mobile money transaction VALUE (%).
  Positive → expanding economic activity → low pressure
  Negative → contracting activity → high pressure

Why YoY and not absolute value? Seasonality is significant in M-Pesa data
(festive peaks, school term patterns), so YoY comparisons strip seasonal noise.
"""
from __future__ import annotations

import re
from typing import Optional

import requests
from loguru import logger

from kppi.data.fetchers.base import BaseFetcher, IndicatorReading

_CBK_PAYMENTS_URL = (
    "https://www.centralbank.go.ke/national-payments-system/mobile-payments/"
)
_HEADERS = {
    "User-Agent": (
        "KPPI/2.0 research-tool "
        "(Kenya Policy Pressure Index - academic/non-commercial)"
    ),
    "Accept": "text/html,application/xhtml+xml",
}

# Match numbers like "7,234.5" or "7234.5" (KES billions or transaction counts)
_NUMBER_RE = re.compile(r"[\d,]+\.?\d*")

# Look for "YoY" or "year-on-year" growth figures directly stated on the page
_YOY_RE = re.compile(
    r"(?:year.on.year|yoy|annual\s+growth)[^\d\-]{0,40}([\-+]?[\d]+\.?[\d]*)\s*%",
    re.IGNORECASE,
)

# Match KES billions figures in a table row: "8,234.56" (with optional commas)
_KES_BN_RE = re.compile(r"\b([\d]{1,3}(?:,[\d]{3})*(?:\.[\d]{1,3})?)\b")


def _parse_yoy_from_page(text: str) -> Optional[float]:
    """
    Attempt to extract a directly-stated YoY growth figure from the page.
    Returns the percentage growth rate, or None if not found.
    """
    m = _YOY_RE.search(text)
    if m:
        val = float(m.group(1))
        if -50.0 <= val <= 100.0:
            logger.debug("M-Pesa YoY (direct): {:.2f}%", val)
            return val
    return None


def _parse_table_values(text: str) -> Optional[float]:
    """
    Attempt to extract consecutive transaction VALUES from HTML tables
    and compute a year-on-year growth rate.

    The CBK table typically has monthly rows; we compare the most recent
    month's value to the same month 12 rows earlier.
    """
    # Find all plausible KES-billions figures in the page (range 1,000–15,000)
    candidates: list[float] = []
    for m in _KES_BN_RE.finditer(text):
        raw = m.group(1).replace(",", "")
        try:
            v = float(raw)
            # Mobile money monthly value in KES billions: realistic range
            if 800.0 <= v <= 15_000.0:
                candidates.append(v)
        except ValueError:
            continue

    if len(candidates) >= 13:
        # Most recent value vs same period last year (12 values back)
        current = candidates[0]
        year_ago = candidates[12]
        if year_ago > 0:
            yoy = round((current - year_ago) / year_ago * 100, 2)
            if -50.0 <= yoy <= 100.0:
                logger.debug(
                    "M-Pesa YoY (table calc): current={:.1f} year_ago={:.1f} → {:.2f}%",
                    current, year_ago, yoy,
                )
                return yoy

    return None


class MPesaVolumeFetcher(BaseFetcher):
    """
    M-Pesa / mobile money transaction volume from CBK payment statistics.

    Returns the YoY growth rate (%) of mobile money transaction value.
    A negative value means contraction → high pressure.
    """

    def fetch(self) -> IndicatorReading:
        response = requests.get(_CBK_PAYMENTS_URL, headers=_HEADERS, timeout=20)
        response.raise_for_status()
        response.encoding = "utf-8"
        text = response.text

        # Try direct YoY figure first
        yoy = _parse_yoy_from_page(text)

        # Fallback: compute from table values
        if yoy is None:
            yoy = _parse_table_values(text)

        if yoy is None:
            raise ValueError(
                "CBK mobile payments page: could not extract M-Pesa YoY growth. "
                "Page layout may have changed."
            )

        return IndicatorReading(
            name="mpesa_volume",
            value=yoy,
            unit="percent_yoy",
            source="CBK - National Payment System statistics",
            notes=(
                f"Mobile money transaction value YoY growth: {yoy:+.1f}% "
                "(positive = expanding, negative = contracting)"
            ),
        )
