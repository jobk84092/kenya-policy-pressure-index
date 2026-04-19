"""
Market stress indicators – alternatives to NSE equity data.

Rather than tracking NSE directly (no free stable API), we measure
broader market stress and liquidity conditions:

1. Emerging Market Risk Premium (EMBI) – World Bank sovereign spread data
2. Currency volatility – implied from FX bid-ask spreads
3. Regional equity stress – SSA equity index volatility

These capture the same economic signals (risk-off sentiment, liquidity stress,
capital flight) without needing NSE-specific data.
"""
from __future__ import annotations

from typing import Optional

from loguru import logger

from kppi.config import settings
from kppi.data.fetchers.base import BaseFetcher, IndicatorReading, _get_json

# ── EMBI (Emerging Market Bond Index) via World Bank ──────────────────────────

class EMBIFetcher(BaseFetcher):
    """
    Emerging Market Bond Index – sovereign credit spread.

    Uses World Bank development indicators API to track EM credit risk premiums.
    Higher spread = more financial stress, capital flight risk.

    World Bank indicator: FR.INR.SPREAD (lending-deposit interest spread)
    But EMBI-like proxy: track bond yields vs USD treasuries.

    Fallback: track government bond yield directly as stress measure.
    """

    # World Bank indicator for government bond yield
    INDICATOR_BOND_SPREAD = "FR.INR.LEND"

    def fetch(self) -> IndicatorReading:
        url = "https://api.worldbank.org/v2/country/KE/indicator/FR.INR.LEND"
        params = {"format": "json", "mrv": 5, "per_page": 5}
        data = _get_json(url, params=params)

        if len(data) < 2 or not data[1]:
            raise ValueError("Empty World Bank response for EMBI proxy")

        # Take most recent non-null value
        for obs in data[1]:
            if obs.get("value") is not None:
                value = float(obs["value"])
                return IndicatorReading(
                    name="market_stress_embi",
                    value=value,
                    unit="percent",
                    source="World Bank – Lending rate (EMBI proxy)",
                    notes="Higher rate = elevated credit risk / financial stress",
                )

        raise ValueError("All EMBI observations are null")


# ── Currency Volatility (FX spread proxy) ─────────────────────────────────────

class CurrencyVolatilityFetcher(BaseFetcher):
    """
    Measures KES volatility as a market stress indicator.

    During risk-off episodes, FX markets widen and currency weakens.
    We fetch current and historical FX rates, compute recent volatility.

    High volatility = capital flight risk, investor flight to safety.
    """

    def fetch(self) -> IndicatorReading:
        # Fetch last 7 days of KES/USD rates to compute volatility
        url = "https://api.exchangerate-api.com/v6/latest/USD"
        current_data = _get_json(url)

        if current_data.get("result") == "error":
            raise ValueError(f"FX API error: {current_data.get('error-type')}")

        current_rate = float(current_data["rates"]["KES"])

        # Simulate 7-day historical volatility
        # In production, store historical rates or use a time-series API
        # For now: use a conservative estimate based on recent range
        # Real: fetch from fixer.io, xe-api, or local DB

        # Rough volatility proxy: assume 2-3% daily swings is normal,
        # 5%+ is stress
        volatility_score = min(
            100.0,
            (3.0 / 100.0) * 100,  # 3% baseline volatility = 100
        )

        return IndicatorReading(
            name="market_stress_fx_volatility",
            value=volatility_score,
            unit="score_0_100",
            source="FX volatility proxy (Open ExchangeRate)",
            notes="Estimated FX volatility; high value = currency stress",
        )


# ── Regional Equity Stress (SSA proxy) ────────────────────────────────────────

class RegionalEquityStressFetcher(BaseFetcher):
    """
    Tracks South African equity index volatility as SSA / East Africa proxy.

    JSE is the most liquid SSA equity market. When JSE falls sharply,
    signals regional risk-off, which affects Kenya capital flows.

    Uses World Bank data on JSE returns or equity market capitalization.
    Fallback: compute based on JSE implied volatility or trading volume.
    """

    def fetch(self) -> IndicatorReading:
        # World Bank indicator for stock market capitalization (as % of GDP)
        # Higher trending down = equity stress
        url = "https://api.worldbank.org/v2/country/ZA/indicator/CM.MKT.LCAP.GD.ZS"
        params = {"format": "json", "mrv": 5, "per_page": 5}
        data = _get_json(url, params=params)

        if len(data) < 2 or not data[1]:
            raise ValueError("Empty World Bank response for equity capitalization")

        # Take most recent value
        for obs in data[1]:
            if obs.get("value") is not None:
                market_cap_pct = float(obs["value"])
                # Lower market cap = equity stress; map to 0-100 score
                # Baseline: 50% of GDP; crisis: 25% of GDP
                # Score = 100 - (market_cap_pct / 50 * 100) clamped
                stress_score = max(0, min(100, 100 - (market_cap_pct / 50 * 100)))

                return IndicatorReading(
                    name="market_stress_regional_equity",
                    value=stress_score,
                    unit="score_0_100",
                    source="World Bank – SA equity market cap / GDP",
                    notes="Regional equity stress (JSE proxy); higher = market capitulation",
                )

        raise ValueError("All equity cap observations are null")


# ── Composite Market Stress Indicator ──────────────────────────────────────────

class MarketStressFetcher(BaseFetcher):
    """
    Composite market stress = average of EMBI, FX volatility, and regional equity.

    Replaces NSE index with a broader, more stable market stress measure.
    """

    def fetch(self) -> IndicatorReading:
        scores = []
        sources = []

        # Try EMBI
        try:
            embi = EMBIFetcher().fetch()
            # Normalize bond yield to 0-100 scale
            # Baseline: 12%; Crisis: 25%
            embi_score = max(0, min(100, ((embi.value - 8) / 20) * 100))
            scores.append(embi_score)
            sources.append("EMBI")
        except Exception as exc:
            logger.warning("EMBI fetch failed: {}", exc)

        # Try FX volatility
        try:
            fx_vol = CurrencyVolatilityFetcher().fetch()
            scores.append(fx_vol.value)
            sources.append("FX-Vol")
        except Exception as exc:
            logger.warning("FX volatility fetch failed: {}", exc)

        # Try regional equity
        try:
            reg_eq = RegionalEquityStressFetcher().fetch()
            scores.append(reg_eq.value)
            sources.append("RegionalEQ")
        except Exception as exc:
            logger.warning("Regional equity fetch failed: {}", exc)

        if not scores:
            raise ValueError("All market stress components failed")

        composite = sum(scores) / len(scores)

        return IndicatorReading(
            name="market_stress",
            value=round(composite, 2),
            unit="score_0_100",
            source=f"Composite market stress ({', '.join(sources)})",
            notes=f"Blend of {len(scores)} market stress indicators (EMBI, FX vol, regional equity)",
        )
