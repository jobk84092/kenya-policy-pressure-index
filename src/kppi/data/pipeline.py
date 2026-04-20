"""
Data pipeline: orchestrates all fetchers into a single snapshot dict.

Each indicator is fetched with a graceful fallback to the last known
value stored in the database.  The pipeline handles partial failures
so the index can still be computed if one source is down.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from loguru import logger

from kppi.config import settings
from kppi.data.fetchers import (
    IndicatorReading,
    InflationFetcher,
    CBKTBillFetcher,
    TBillRateFetcher,
    FXRateFetcher,
    PoliticalPressureFetcher,
    KenyaNewsPoliticalFetcher,
    NASIFetcher,
    ForexReservesFetcher,
    WorldBankReservesFetcher,
    EurobondSpreadFetcher,
    MPesaVolumeFetcher,
    MockInflationFetcher,
    MockFXRateFetcher,
    MockBondYieldFetcher,
    MockMarketStressFetcher,
    MockPoliticalFetcher,
    MockForexReservesFetcher,
    MockEurobondSpreadFetcher,
    MockMPesaVolumeFetcher,
)


# Market stress indicator: live NASI index from nseinsider.co.ke
# No API key required; falls back to mock when the site is unreachable


@dataclass
class RawSnapshot:
    """All raw indicator readings at a single point in time."""

    inflation: Optional[IndicatorReading] = None
    fx_rate: Optional[IndicatorReading] = None
    bond_yield: Optional[IndicatorReading] = None
    market_stress: Optional[IndicatorReading] = None
    political_pressure: Optional[IndicatorReading] = None
    forex_reserves: Optional[IndicatorReading] = None
    eurobond_spread: Optional[IndicatorReading] = None
    mpesa_volume: Optional[IndicatorReading] = None
    fetched_at: datetime = field(default_factory=datetime.utcnow)

    def as_dict(self) -> dict:
        result = {"fetched_at": self.fetched_at.isoformat()}
        for name in (
            "inflation", "fx_rate", "bond_yield", "market_stress",
            "political_pressure", "forex_reserves", "eurobond_spread", "mpesa_volume",
        ):
            reading: Optional[IndicatorReading] = getattr(self, name)
            result[name] = reading.value if reading else None
            result[f"{name}_source"] = reading.source if reading else "missing"
        return result

    @property
    def is_complete(self) -> bool:
        return all(
            getattr(self, name) is not None
            for name in (
                "inflation", "fx_rate", "bond_yield", "market_stress",
                "political_pressure", "forex_reserves", "eurobond_spread", "mpesa_volume",
            )
        )

    @property
    def missing_indicators(self) -> list[str]:
        return [
            name
            for name in (
                "inflation", "fx_rate", "bond_yield", "market_stress",
                "political_pressure", "forex_reserves", "eurobond_spread", "mpesa_volume",
            )
            if getattr(self, name) is None
        ]


class DataPipeline:
    """
    Runs all fetchers concurrently-ish (sequential for simplicity; each
    call is I/O-bound with built-in retries).

    Usage::

        pipeline = DataPipeline()
        snapshot = pipeline.run()
    """

    def __init__(self) -> None:
        self._use_mock = settings.use_mock_data

    # ── Inflation ─────────────────────────────────────────────────────────────
    def _fetch_inflation(self) -> Optional[IndicatorReading]:
        if self._use_mock:
            return MockInflationFetcher().safe_fetch()
        reading = InflationFetcher().safe_fetch()
        if reading is None:
            logger.warning("Live inflation fetch failed; falling back to mock")
            reading = MockInflationFetcher().safe_fetch()
        return reading

    # ── FX Rate ───────────────────────────────────────────────────────────────
    def _fetch_fx_rate(self) -> Optional[IndicatorReading]:
        if self._use_mock:
            return MockFXRateFetcher().safe_fetch()
        reading = FXRateFetcher().safe_fetch()
        if reading is None:
            logger.warning("Live FX fetch failed; falling back to mock")
            reading = MockFXRateFetcher().safe_fetch()
        return reading

    # ── Bond Yield ────────────────────────────────────────────────────────────
    def _fetch_bond_yield(self) -> Optional[IndicatorReading]:
        if self._use_mock:
            return MockBondYieldFetcher().safe_fetch()
        # Primary: CBK direct (weekly auction results, always current)
        reading = CBKTBillFetcher().safe_fetch()
        if reading is not None:
            return reading
        logger.warning("CBK T-bill fetch failed; trying World Bank fallback")
        # Secondary: World Bank (updated with a lag, but free)
        reading = TBillRateFetcher().safe_fetch()
        if reading is None:
            logger.warning("Live bond yield fetch failed; falling back to mock")
            reading = MockBondYieldFetcher().safe_fetch()
        return reading

    # ── Market Stress (NASI) ──────────────────────────────────────────────────
    def _fetch_market_stress(self) -> Optional[IndicatorReading]:
        if self._use_mock:
            return MockMarketStressFetcher().safe_fetch()
        # Primary: live NASI index level from nseinsider.co.ke daily briefs
        reading = NASIFetcher().safe_fetch()
        if reading is not None:
            return reading
        logger.warning("NASI fetch failed; falling back to mock")
        return MockMarketStressFetcher().safe_fetch()

    # ── Political Pressure ────────────────────────────────────────────────────
    def _fetch_political(self) -> Optional[IndicatorReading]:
        if self._use_mock:
            return MockPoliticalFetcher().safe_fetch()

        # Primary: Kenya-focused political pressure from Google News RSS
        kenya_news = KenyaNewsPoliticalFetcher().safe_fetch()

        # Secondary: GDELT (global news volume + tone, real-time)
        gdelt = PoliticalPressureFetcher().safe_fetch()

        if kenya_news is not None and gdelt is not None:
            # Blend: Kenya-specific signal slightly outweighs global coverage.
            blended = round(0.60 * kenya_news.value + 0.40 * gdelt.value, 2)
            logger.debug(
                "Political blend: KenyaNews={:.1f}, GDELT={:.1f} -> blended={:.1f}",
                kenya_news.value, gdelt.value, blended,
            )
            return IndicatorReading(
                name="political_pressure",
                value=blended,
                unit="score_0_100",
                source="KenyaNews (60%) + GDELT (40%)",
                notes=(
                    f"KenyaNews={kenya_news.value:.1f}: {kenya_news.notes} | "
                    f"GDELT={gdelt.value:.1f}: {gdelt.notes}"
                ),
            )
        elif kenya_news is not None:
            logger.info("Political: KenyaNews only (GDELT unavailable)")
            return kenya_news
        elif gdelt is not None:
            logger.info("Political: GDELT only (KenyaNews unavailable)")
            return gdelt
        else:
            logger.warning("All political fetchers failed; falling back to mock")
            return MockPoliticalFetcher().safe_fetch()

    # ── Orchestrator ────────────────────────────────────────────────
    # ── Forex Reserves ───────────────────────────────────────────
    def _fetch_forex_reserves(self) -> Optional[IndicatorReading]:
        if self._use_mock:
            return MockForexReservesFetcher().safe_fetch()
        # Primary: CBK MPC posts
        reading = ForexReservesFetcher().safe_fetch()
        if reading is not None:
            return reading
        logger.warning("CBK forex reserves fetch failed; trying World Bank fallback (60s timeout)")
        # Fallback: World Bank computed (annual, ~1yr lag, 60s timeout)
        reading = WorldBankReservesFetcher().safe_fetch()
        if reading is None:
            logger.error("All live forex reserves sources failed; indicator will be excluded this cycle")
        return reading  # None → calculator substitutes neutral 50

    # ── Eurobond Spread ─────────────────────────────────────────
    def _fetch_eurobond_spread(self) -> Optional[IndicatorReading]:
        if self._use_mock:
            return MockEurobondSpreadFetcher().safe_fetch()
        reading = EurobondSpreadFetcher().safe_fetch()
        if reading is None:
            logger.warning("Eurobond spread: no live source available; indicator excluded this cycle")
        return reading  # None → calculator substitutes neutral 50

    # ── M-Pesa Volume ────────────────────────────────────────────
    def _fetch_mpesa_volume(self) -> Optional[IndicatorReading]:
        if self._use_mock:
            return MockMPesaVolumeFetcher().safe_fetch()
        reading = MPesaVolumeFetcher().safe_fetch()
        if reading is None:
            logger.warning("M-Pesa volume fetch failed; falling back to mock")
            reading = MockMPesaVolumeFetcher().safe_fetch()
        return reading

    # ── Orchestrator ──────────────────────────────────────────────────────────
    def run(self) -> RawSnapshot:
        logger.info("DataPipeline: starting data collection (mock={})", self._use_mock)

        snapshot = RawSnapshot(
            inflation=self._fetch_inflation(),
            fx_rate=self._fetch_fx_rate(),
            bond_yield=self._fetch_bond_yield(),
            market_stress=self._fetch_market_stress(),
            political_pressure=self._fetch_political(),
            forex_reserves=self._fetch_forex_reserves(),
            eurobond_spread=self._fetch_eurobond_spread(),
            mpesa_volume=self._fetch_mpesa_volume(),
        )

        if snapshot.is_complete:
            logger.info("DataPipeline: all indicators fetched successfully")
        else:
            logger.warning(
                "DataPipeline: missing indicators – {}",
                snapshot.missing_indicators,
            )

        return snapshot
