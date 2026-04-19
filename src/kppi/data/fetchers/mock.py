"""
Mock / demo data fetchers.

Returns plausible synthetic values that mirror recent Kenya macro conditions.
Activated when `USE_MOCK_DATA=true` in the environment, or when all live
API calls fail and a fallback is needed.
"""
from __future__ import annotations

import random
from datetime import datetime

from kppi.data.fetchers.base import BaseFetcher, IndicatorReading

# Central reference values (approximate recent Kenya macro)
_MOCK_INFLATION = 6.5       # % YoY
_MOCK_FX_RATE = 148.5       # KES per USD
_MOCK_BOND_YIELD = 16.2     # Treasury bill/bond rate %
_MOCK_NASI = 162.0          # NASI index level (nasi_baseline default ~160)
_MOCK_POLITICAL = 45.0      # Political pressure score (0–100)

# Noise factor ± applied to each call for realism in demos
_NOISE = 0.03


def _jitter(base: float, pct: float = _NOISE) -> float:
    """Add small random noise to avoid static display values."""
    delta = base * pct
    return round(base + random.uniform(-delta, delta), 4)


class MockInflationFetcher(BaseFetcher):
    def fetch(self) -> IndicatorReading:
        return IndicatorReading(
            name="inflation",
            value=_jitter(_MOCK_INFLATION),
            unit="percent_yoy",
            source="mock",
            notes="Synthetic demo value – enable live fetchers for real data",
        )


class MockFXRateFetcher(BaseFetcher):
    def fetch(self) -> IndicatorReading:
        return IndicatorReading(
            name="fx_rate",
            value=_jitter(_MOCK_FX_RATE),
            unit="KES_per_USD",
            source="mock",
        )


class MockBondYieldFetcher(BaseFetcher):
    def fetch(self) -> IndicatorReading:
        return IndicatorReading(
            name="bond_yield",
            value=_jitter(_MOCK_BOND_YIELD),
            unit="percent",
            source="mock",
            notes="Proxy for 91-day T-bill rate",
        )


class MockMarketStressFetcher(BaseFetcher):
    def fetch(self) -> IndicatorReading:
        return IndicatorReading(
            name="market_stress",
            value=_jitter(_MOCK_NASI),
            unit="nasi_index_level",
            source="mock",
            notes="Synthetic NASI level – enable NASIFetcher for real data",
        )


class MockPoliticalFetcher(BaseFetcher):
    def fetch(self) -> IndicatorReading:
        return IndicatorReading(
            name="political_pressure",
            value=_jitter(_MOCK_POLITICAL),
            unit="score_0_100",
            source="mock",
        )


# ── New indicator mocks ───────────────────────────────────────────────────────

_MOCK_FOREX_RESERVES = 4.8    # months of import cover (Kenya ~4.5–5 months recently)
_MOCK_EUROBOND_SPREAD = 7.5   # pp above US 10yr (Kenya typical range 6–10 pp)
_MOCK_MPESA_YOY = 12.0        # % YoY growth in M-Pesa transaction value


class MockForexReservesFetcher(BaseFetcher):
    def fetch(self) -> IndicatorReading:
        return IndicatorReading(
            name="forex_reserves",
            value=_jitter(_MOCK_FOREX_RESERVES),
            unit="months_import_cover",
            source="mock",
            notes="Synthetic demo value – enable ForexReservesFetcher for real data",
        )


class MockEurobondSpreadFetcher(BaseFetcher):
    def fetch(self) -> IndicatorReading:
        return IndicatorReading(
            name="eurobond_spread",
            value=_jitter(_MOCK_EUROBOND_SPREAD),
            unit="percentage_points",
            source="mock",
            notes="Synthetic demo value – enable EurobondSpreadFetcher for real data",
        )


class MockMPesaVolumeFetcher(BaseFetcher):
    def fetch(self) -> IndicatorReading:
        return IndicatorReading(
            name="mpesa_volume",
            value=_jitter(_MOCK_MPESA_YOY),
            unit="percent_yoy",
            source="mock",
            notes="Synthetic demo value – enable MPesaVolumeFetcher for real data",
        )
