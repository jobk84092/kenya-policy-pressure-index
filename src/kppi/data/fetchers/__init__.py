"""Fetchers sub-package – public re-exports."""
from kppi.data.fetchers.base import BaseFetcher, IndicatorReading
from kppi.data.fetchers.worldbank import InflationFetcher, TBillRateFetcher, CBKTBillFetcher
from kppi.data.fetchers.exchangerate import FXRateFetcher
from kppi.data.fetchers.gdelt import PoliticalPressureFetcher
from kppi.data.fetchers.kenya_news import KenyaNewsPoliticalFetcher
from kppi.data.fetchers.nasi import NASIFetcher
from kppi.data.fetchers.forex_reserves import ForexReservesFetcher, WorldBankReservesFetcher
from kppi.data.fetchers.eurobond import EurobondSpreadFetcher
from kppi.data.fetchers.mpesa import MPesaVolumeFetcher
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
    MockForexReservesFetcher,
    MockEurobondSpreadFetcher,
    MockMPesaVolumeFetcher,
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
    "ForexReservesFetcher",
    "WorldBankReservesFetcher",
    "EurobondSpreadFetcher",
    "MPesaVolumeFetcher",
    "MarketStressFetcher",
    "EMBIFetcher",
    "CurrencyVolatilityFetcher",
    "RegionalEquityStressFetcher",
    "MockInflationFetcher",
    "MockFXRateFetcher",
    "MockBondYieldFetcher",
    "MockMarketStressFetcher",
    "MockPoliticalFetcher",
    "MockForexReservesFetcher",
    "MockEurobondSpreadFetcher",
    "MockMPesaVolumeFetcher",
]
