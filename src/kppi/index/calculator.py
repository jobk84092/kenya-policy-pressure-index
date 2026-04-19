"""
KPPI composite index calculator.

Takes a `RawSnapshot` (from the data pipeline) and produces a `KPPIResult`
containing:
  - Individual normalised component scores (0–100 each)
  - The weighted composite KPPI score (0–100)
  - A human-readable pressure tier label
  - Metadata for storage / display
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from loguru import logger

from kppi.config import settings
from kppi.data.pipeline import RawSnapshot
from kppi.index.normalizer import (
    normalise_inflation,
    normalise_fx_rate,
    normalise_bond_yield,
    normalise_market_stress,
    normalise_political,
)


# ── Pressure tier thresholds ──────────────────────────────────────────────────

TIER_LABELS = [
    (0,  30, "Low",      "🟢",  "Stable – no significant stress signals"),
    (30, 50, "Moderate", "🟡",  "Watch – some economic or political headwinds"),
    (50, 70, "High",     "🟠",  "Elevated – material stress, monitor closely"),
    (70, 85, "Severe",   "🔴",  "Severe – multiple stress factors compounding"),
    (85, 101,"Crisis",   "🚨",  "Crisis – acute instability across indicators"),
]


def _get_tier(score: float) -> tuple[str, str, str]:
    """Returns (label, emoji, description) for a given composite score."""
    for lo, hi, label, emoji, desc in TIER_LABELS:
        if lo <= score < hi:
            return label, emoji, desc
    return "Crisis", "🚨", "Extreme values"


# ── Result data class ─────────────────────────────────────────────────────────

@dataclass
class ComponentScores:
    """Normalised component scores (0–100 each)."""
    inflation: float
    fx_rate: float
    bond_yield: float
    market_stress: float
    political: float

    def as_dict(self) -> dict[str, float]:
        return {
            "inflation": self.inflation,
            "fx_rate": self.fx_rate,
            "bond_yield": self.bond_yield,
            "market_stress": self.market_stress,
            "political": self.political,
        }


@dataclass
class KPPIResult:
    """Full result of a single KPPI computation."""

    composite_score: float
    components: ComponentScores
    tier: str
    tier_emoji: str
    tier_description: str
    confidence_score: float
    confidence_label: str
    confidence_notes: str
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # Raw values for traceability
    raw_inflation: Optional[float] = None
    raw_fx_rate: Optional[float] = None
    raw_bond_yield: Optional[float] = None
    raw_market_stress: Optional[float] = None
    raw_political: Optional[float] = None

    # 4-week moving average of political (set by jobs.py after DB query)
    political_smoothed: Optional[float] = None

    def as_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "composite_score": self.composite_score,
            "tier": self.tier,
            "tier_emoji": self.tier_emoji,
            "tier_description": self.tier_description,
            "confidence_score": self.confidence_score,
            "confidence_label": self.confidence_label,
            "confidence_notes": self.confidence_notes,
            # Normalised components
            "score_inflation": self.components.inflation,
            "score_fx_rate": self.components.fx_rate,
            "score_bond_yield": self.components.bond_yield,
            "score_market_stress": self.components.market_stress,
            "score_political": self.components.political,
            # Raw values
            "raw_inflation": self.raw_inflation,
            "raw_fx_rate": self.raw_fx_rate,
            "raw_bond_yield": self.raw_bond_yield,
            "raw_market_stress": self.raw_market_stress,
            "raw_political": self.raw_political,
            # Smoothed political (None until enough history is available)
            "political_smoothed": self.political_smoothed,
        }

    def summary(self) -> str:
        return (
            f"KPPI {self.composite_score:.1f}/100 | "
            f"{self.tier_emoji} {self.tier} | "
            f"{self.tier_description} | "
            f"confidence {self.confidence_score:.0f}% ({self.confidence_label})"
        )


# ── Calculator ────────────────────────────────────────────────────────────────

class KPPICalculator:
    """
    Computes the KPPI composite index from a `RawSnapshot`.

    The composite score is the weighted sum of normalised component scores.
    Missing indicators are handled by substituting the historical mean (50)
    for that component, logged as a warning.
    """

    _MISSING_SUBSTITUTE = 50.0  # neutral / midpoint score for missing data

    def __init__(self) -> None:
        self._weights = {
            "inflation": settings.weight_inflation,
            "fx_rate":   settings.weight_fx,
            "bond_yield":settings.weight_bond,
            "market_stress":settings.weight_market_stress,
            "political": settings.weight_political,
        }

    def _assess_confidence(self, snapshot: RawSnapshot) -> tuple[float, str, str]:
        """Estimate data quality confidence (0-100) from source/fallback usage."""
        score = 100.0
        flags: list[str] = []

        indicators = {
            "inflation": snapshot.inflation,
            "fx_rate": snapshot.fx_rate,
            "bond_yield": snapshot.bond_yield,
            "market_stress": snapshot.market_stress,
            "political": snapshot.political_pressure,
        }

        for name, reading in indicators.items():
            if reading is None:
                score -= 25
                flags.append(f"missing {name}")
                continue

            source = (reading.source or "").lower()
            if "mock" in source:
                score -= 20
                flags.append(f"{name} from mock")
            elif "fallback" in source:
                score -= 12
                flags.append(f"{name} from fallback")

        # Domain sanity checks for values that should never be <= 0 in practice.
        if snapshot.bond_yield is not None and snapshot.bond_yield.value <= 0:
            score -= 10
            flags.append("bond_yield non-positive")
        if snapshot.market_stress is not None and snapshot.market_stress.value <= 0:
            score -= 10
            flags.append("market_stress non-positive")

        # Single-source political penalty: blended source contains "+";
        # a single-source reading means one signal failed and we can't cross-check.
        pol = snapshot.political_pressure
        if pol is not None and "+" not in (pol.source or ""):
            score -= 8
            flags.append("political single-source")

        score = round(max(0.0, min(100.0, score)), 1)
        if score >= 85:
            label = "High"
        elif score >= 70:
            label = "Medium"
        else:
            label = "Low"

        notes = "; ".join(flags) if flags else "all indicators live and plausible"
        return score, label, notes

    def compute(self, snapshot: RawSnapshot) -> KPPIResult:
        cfg = settings

        # ── Normalise each component ───────────────────────────────────────
        def _val(reading, fallback: float) -> tuple[float, float]:
            """Returns (raw_value, normalised_score)."""
            if reading is None:
                logger.warning("Missing indicator reading; substituting {}", fallback)
                return fallback, self._MISSING_SUBSTITUTE
            return reading.value, reading.value  # raw; normalisation applied below

        raw_inf  = snapshot.inflation.value   if snapshot.inflation   else None
        raw_fx   = snapshot.fx_rate.value     if snapshot.fx_rate     else None
        raw_bond = snapshot.bond_yield.value  if snapshot.bond_yield  else None
        raw_stress = snapshot.market_stress.value if snapshot.market_stress else None
        raw_pol  = snapshot.political_pressure.value if snapshot.political_pressure else None

        score_inf  = normalise_inflation(raw_inf)   if raw_inf  is not None else self._MISSING_SUBSTITUTE
        score_fx   = normalise_fx_rate(raw_fx, cfg.fx_baseline)  if raw_fx   is not None else self._MISSING_SUBSTITUTE
        score_bond = normalise_bond_yield(raw_bond) if raw_bond is not None else self._MISSING_SUBSTITUTE
        score_stress = normalise_market_stress(raw_stress, cfg.nasi_baseline) if raw_stress is not None else self._MISSING_SUBSTITUTE
        score_pol  = normalise_political(raw_pol)   if raw_pol  is not None else self._MISSING_SUBSTITUTE

        components = ComponentScores(
            inflation=round(score_inf,  2),
            fx_rate=round(score_fx,   2),
            bond_yield=round(score_bond, 2),
            market_stress=round(score_stress,  2),
            political=round(score_pol,  2),
        )

        # ── Weighted composite ─────────────────────────────────────────────
        composite = (
            self._weights["inflation"]  * components.inflation +
            self._weights["fx_rate"]    * components.fx_rate   +
            self._weights["bond_yield"] * components.bond_yield +
            self._weights["market_stress"] * components.market_stress +
            self._weights["political"]  * components.political
        )
        composite = round(composite, 2)

        tier, emoji, desc = _get_tier(composite)
        confidence_score, confidence_label, confidence_notes = self._assess_confidence(snapshot)

        result = KPPIResult(
            composite_score=composite,
            components=components,
            tier=tier,
            tier_emoji=emoji,
            tier_description=desc,
            confidence_score=confidence_score,
            confidence_label=confidence_label,
            confidence_notes=confidence_notes,
            timestamp=snapshot.fetched_at,
            raw_inflation=raw_inf,
            raw_fx_rate=raw_fx,
            raw_bond_yield=raw_bond,
            raw_market_stress=raw_stress,
            raw_political=raw_pol,
        )

        logger.info(result.summary())
        return result
