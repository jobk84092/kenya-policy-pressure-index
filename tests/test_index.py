"""
Tests for the normaliser functions and KPPI composite calculator.
"""
from __future__ import annotations

import pytest

from kppi.index.normalizer import (
    normalise_inflation,
    normalise_fx_rate,
    normalise_bond_yield,
    normalise_market_stress,
    normalise_political,
)
from kppi.index.calculator import KPPICalculator, KPPIResult
from kppi.data.fetchers.base import IndicatorReading
from kppi.data.pipeline import RawSnapshot
from datetime import datetime


# ── Normaliser unit tests ─────────────────────────────────────────────────────

class TestNormaliseInflation:
    @pytest.mark.parametrize("pct, expected_range", [
        (0.0, (0, 5)),
        (3.0, (5, 15)),
        (5.0, (20, 30)),
        (10.0, (50, 60)),
        (15.0, (70, 80)),
        (25.0, (95, 100)),
    ])
    def test_monotone_increase(self, pct, expected_range):
        score = normalise_inflation(pct)
        lo, hi = expected_range
        assert lo <= score <= hi, f"inflation={pct}% → score={score} not in [{lo},{hi}]"

    def test_score_clamped_to_100(self):
        assert normalise_inflation(100.0) == 100.0

    def test_score_non_negative(self):
        assert normalise_inflation(-5.0) >= 0.0


class TestNormaliseFX:
    def test_at_baseline_gives_low_score(self):
        assert normalise_fx_rate(110.0, baseline=110.0) == 0.0

    def test_strong_depreciation_gives_high_score(self):
        # 80% above baseline should be near 100
        assert normalise_fx_rate(198.0, baseline=110.0) >= 95

    def test_appreciation_gives_zero(self):
        # Stronger shilling should not increase pressure
        assert normalise_fx_rate(90.0, baseline=110.0) == 0.0

    def test_invalid_baseline_raises(self):
        with pytest.raises(ValueError):
            normalise_fx_rate(150.0, baseline=0)

    def test_score_clamped_to_100(self):
        assert normalise_fx_rate(10_000.0, baseline=110.0) == 100.0


class TestNormaliseBondYield:
    def test_low_yield_gives_zero(self):
        assert normalise_bond_yield(5.0) == 0.0

    def test_baseline_yield_gives_moderate(self):
        score = normalise_bond_yield(12.0)
        assert 20 <= score <= 30

    def test_very_high_yield_gives_max(self):
        assert normalise_bond_yield(30.0) == 100.0


class TestNormaliseNSE:
    def test_at_baseline_gives_zero(self):
        assert normalise_market_stress(160.0, baseline=160.0) == 0.0

    def test_above_baseline_gives_zero(self):
        # A rising market should not increase pressure
        assert normalise_market_stress(180.0, baseline=160.0) == 0.0

    def test_ten_pct_decline_gives_25(self):
        # 10% decline from 160 → NASI at 144
        assert normalise_market_stress(144.0, baseline=160.0) == 25.0

    def test_fifty_pct_decline_gives_100(self):
        # 50% decline from 160 → NASI at 80
        assert normalise_market_stress(80.0, baseline=160.0) == 100.0

    def test_max_value_bounded(self):
        assert normalise_market_stress(0.0, baseline=160.0) == 100.0

    def test_invalid_baseline_raises(self):
        with pytest.raises(ValueError):
            normalise_market_stress(160.0, baseline=0.0)
class TestNormalisePolitical:
    def test_zero_gives_zero(self):
        assert normalise_political(0.0) == 0.0
    def test_high_score_is_soft_capped(self):
        score_80 = normalise_political(80.0)
        score_100 = normalise_political(100.0)
        assert score_100 > score_80
        assert score_100 < 100.0  # capped

    def test_midrange_pass_through(self):
        assert normalise_political(50.0) == 50.0


# ── Calculator integration tests ──────────────────────────────────────────────

def _make_reading(name: str, value: float, unit: str = "test") -> IndicatorReading:
    return IndicatorReading(name=name, value=value, unit=unit, source="test")


def _make_snapshot(**overrides) -> RawSnapshot:
    defaults = dict(
        inflation=_make_reading("inflation", 6.5, "percent_yoy"),
        fx_rate=_make_reading("fx_rate", 148.5, "KES_per_USD"),
        bond_yield=_make_reading("bond_yield", 16.0, "percent"),
        market_stress=_make_reading("market_stress", 158.0, "nasi_index_level"),
        political_pressure=_make_reading("political_pressure", 45.0, "score_0_100"),
    )
    defaults.update(overrides)
    return RawSnapshot(**defaults, fetched_at=datetime.utcnow())


class TestKPPICalculator:
    def test_returns_kppi_result(self):
        snap = _make_snapshot()
        result = KPPICalculator().compute(snap)
        assert isinstance(result, KPPIResult)

    def test_score_in_valid_range(self):
        snap = _make_snapshot()
        result = KPPICalculator().compute(snap)
        assert 0 <= result.composite_score <= 100

    def test_tier_assigned(self):
        snap = _make_snapshot()
        result = KPPICalculator().compute(snap)
        assert result.tier in ("Low", "Moderate", "High", "Severe", "Crisis")

    def test_high_stress_snapshot_has_high_score(self):
        snap = _make_snapshot(
            inflation=_make_reading("inflation", 20.0),
            fx_rate=_make_reading("fx_rate", 230.0),
            bond_yield=_make_reading("bond_yield", 25.0),
            market_stress=_make_reading("market_stress", 80.0),   # 50% decline from baseline=160
            political_pressure=_make_reading("political_pressure", 90.0),
        )
        result = KPPICalculator().compute(snap)
        assert result.composite_score >= 70, "Extreme stress should produce Severe+ tier"

    def test_low_stress_snapshot_has_low_score(self):
        snap = _make_snapshot(
            inflation=_make_reading("inflation", 2.0),
            fx_rate=_make_reading("fx_rate", 105.0),
            bond_yield=_make_reading("bond_yield", 7.0),
            market_stress=_make_reading("market_stress", 170.0),  # above baseline=160 → 0 stress
            political_pressure=_make_reading("political_pressure", 5.0),
        )
        result = KPPICalculator().compute(snap)
        assert result.composite_score <= 30, "Benign conditions should be Low tier"

    def test_missing_indicator_substituted(self):
        snap = _make_snapshot(political_pressure=None)
        result = KPPICalculator().compute(snap)
        # Should not raise; missing political uses midpoint substitute
        assert result.composite_score is not None
        assert result.confidence_score < 100

    def test_as_dict_contains_required_keys(self):
        result = KPPICalculator().compute(_make_snapshot())
        d = result.as_dict()
        required = {
            "timestamp", "composite_score", "tier",
            "confidence_score", "confidence_label", "confidence_notes",
            "score_inflation", "score_fx_rate", "score_bond_yield",
            "score_market_stress", "score_political",
        }
        assert required.issubset(d.keys())

    def test_confidence_range_and_label(self):
        result = KPPICalculator().compute(_make_snapshot())
        assert 0 <= result.confidence_score <= 100
        assert result.confidence_label in ("High", "Medium", "Low")

    def test_summary_string_format(self):
        result = KPPICalculator().compute(_make_snapshot())
        summary = result.summary()
        assert "KPPI" in summary
        assert result.tier in summary
