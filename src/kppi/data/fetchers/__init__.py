"""Fetchers sub-package – public re-exports."""
from kppi.data.fetchers.base import BaseFetcher, IndicatorReading
from kppi.data.fetchers.worldbank import InflationFetcher, TBillRateFetcher, CBKTBillFetcher
from kppi.data.fetchers.exchangerate import FXRateFetcher
from kppi.data.fetchers.gdelt import PoliticalPressureFetcher
from kppi.data.fetchers.kenya_news import KenyaNewsPoliticalFetcher
from kppi.data.fetchers.nasi import NASIFetcher
from kppi.data.fetchers.market_stress import (
    MarketStressFetcher,
    EMBIFetcher,
    CurrencyVolatilityFetcher,
    RegionalEquityStressFetcher,
)
from kppi.data.fetchers.mock import (
    MockInflationFetcher,
    MockFXRateFetcher,
    MockBondYieldFetcher,
    MockMarketStressFetcher,
    MockPoliticalFetcher,
)

__all__ = [
    "BaseFetcher",
    "IndicatorReading",
    "InflationFetcher",
    "TBillRateFetcher",
    "CBKTBillFetcher",
    "FXRateFetcher",
    "PoliticalPressureFetcher",
    "KenyaNewsPoliticalFetcher",
    "NASIFetcher",
    "MarketStressFetcher",
    "EMBIFetcher",
    "CurrencyVolatilityFetcher",
    "RegionalEquityStressFetcher",
    "MockInflationFetcher",
    "MockFXRateFetcher",
    "MockBondYieldFetcher",
    "MockMarketStressFetcher",
    "MockPoliticalFetcher",
]
