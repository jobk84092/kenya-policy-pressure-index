"""
Exchange rate fetcher – KES / USD.

Uses the free, no-auth Open ExchangeRate API endpoint.
If an API key is configured, the authenticated endpoint is used instead
(higher rate limits).

Docs: https://www.exchangerate-api.com/docs/free
"""
from __future__ import annotations

from loguru import logger

from kppi.config import settings
from kppi.data.fetchers.base import BaseFetcher, IndicatorReading, _get_json

_FREE_URL = "https://open.er-api.com/v6/latest/USD"
_AUTH_URL = "https://v6.exchangerate-api.com/v6/{key}/latest/USD"


class FXRateFetcher(BaseFetcher):
    """
    Fetches the current USD/KES exchange rate.
    A higher rate means KES has depreciated, indicating economic stress.
    """

    def fetch(self) -> IndicatorReading:
        if settings.exchangerate_api_key:
            url = _AUTH_URL.format(key=settings.exchangerate_api_key)
            source_tag = "ExchangeRate-API (authenticated)"
        else:
            url = _FREE_URL
            source_tag = "Open ExchangeRate API (free)"

        data = _get_json(url)

        if data.get("result") == "error":
            raise ValueError(f"ExchangeRate API error: {data.get('error-type', 'unknown')}")

        rates: dict = data.get("rates", {})
        kes_rate = rates.get("KES")
        if kes_rate is None:
            raise KeyError("KES not found in exchange rate response")

        return IndicatorReading(
            name="fx_rate",
            value=float(kes_rate),
            unit="KES_per_USD",
            source=source_tag,
            notes="How many KES buy 1 USD; higher value = weaker shilling",
        )
