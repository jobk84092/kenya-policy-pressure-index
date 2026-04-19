"""
Normalises raw indicator values to a 0–100 pressure scale.

Convention
----------
  0   = no stress / ideal conditions
  100 = extreme stress / crisis

Each indicator uses a monotone piecewise-linear mapping anchored to
Kenyan historical data.  The breakpoints can be tuned via Settings.
"""
from __future__ import annotations


def _piecewise_linear(value: float, breakpoints: list[tuple[float, float]]) -> float:
    """
    Interpolate `value` against a sorted list of (raw_value, score) pairs.

    Values below the first breakpoint → 0.
    Values above the last breakpoint → 100.
    Intermediate values are linearly interpolated.
    """
    if value <= breakpoints[0][0]:
        return breakpoints[0][1]
    if value >= breakpoints[-1][0]:
        return breakpoints[-1][1]

    for i in range(len(breakpoints) - 1):
        x0, y0 = breakpoints[i]
        x1, y1 = breakpoints[i + 1]
        if x0 <= value <= x1:
            t = (value - x0) / (x1 - x0)
            return y0 + t * (y1 - y0)

    return 0.0  # unreachable, satisfies type checkers


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


# ── Individual normaliser functions ───────────────────────────────────────────

def normalise_inflation(inflation_pct: float) -> float:
    """
    Annual CPI inflation (%) → pressure score 0–100.

    Breakpoints calibrated to Kenya's historical range:
      ≤3 %   → very low pressure (10)
       5 %   → baseline / normal (25)
      10 %   → elevated (55)
      15 %   → high (75)
      ≥20 %  → crisis (100)
    """
    bp = [
        (0.0,  0.0),
        (3.0,  10.0),
        (5.0,  25.0),
        (10.0, 55.0),
        (15.0, 75.0),
        (20.0, 100.0),
    ]
    return _clamp(_piecewise_linear(inflation_pct, bp))


def normalise_fx_rate(kes_per_usd: float, baseline: float = 110.0) -> float:
    """
    KES/USD exchange rate → pressure score 0–100.

    Measures % depreciation vs the `baseline` reference.
    The baseline should be the long-run "calm" rate.

      ≤baseline  → low pressure (0)
      +15 %      → 30
      +30 %      → 55
      +50 %      → 75
      +80 %      → 100
    """
    if baseline <= 0:
        raise ValueError("FX baseline must be positive")

    depreciation_pct = ((kes_per_usd - baseline) / baseline) * 100
    bp = [
        (0.0,  0.0),
        (15.0, 30.0),
        (30.0, 55.0),
        (50.0, 75.0),
        (80.0, 100.0),
    ]
    return _clamp(_piecewise_linear(depreciation_pct, bp))


def normalise_bond_yield(yield_pct: float) -> float:
    """
    Government bond / T-bill yield (%) → pressure score 0–100.

    Higher yields signal increased risk premium / fiscal stress.
      ≤8 %   → 0
      12 %   → 25
      16 %   → 55
      20 %   → 80
      ≥25 %  → 100
    """
    bp = [
        (0.0,  0.0),
        (8.0,  0.0),
        (12.0, 25.0),
        (16.0, 55.0),
        (20.0, 80.0),
        (25.0, 100.0),
    ]
    return _clamp(_piecewise_linear(yield_pct, bp))


def normalise_market_stress(nasi_value: float, baseline: float = 160.0) -> float:
    """
    NASI (NSE All Share Index) level → pressure score 0–100.

    Higher NASI = stronger equity market = lower stress (inverted scale).
    Pressure rises as the index declines relative to the baseline.

      ≥ baseline   → 0    (market at or above normal)
      − 10 %       → 25
      − 20 %       → 50
      − 35 %       → 75
      ≤ − 50 %     → 100  (market in crisis)

    The ``baseline`` should be the long-run "calm" NASI level
    (configured via NASI_BASELINE env var; default 160).
    """
    if baseline <= 0:
        raise ValueError("NASI baseline must be positive")

    decline_pct = ((baseline - nasi_value) / baseline) * 100
    bp = [
        (0.0,  0.0),
        (10.0, 25.0),
        (20.0, 50.0),
        (35.0, 75.0),
        (50.0, 100.0),
    ]
    return _clamp(_piecewise_linear(decline_pct, bp))


def normalise_political(score_0_100: float) -> float:
    """
    Political pressure raw score (already 0–100 from GDELT fetcher) → 0–100.
    Applies light smoothing so extreme one-off events don't dominate.
    """
    # Soft cap: scores above 80 are treated as 80 + remainder/2
    if score_0_100 > 80.0:
        capped = 80.0 + (score_0_100 - 80.0) * 0.5
    else:
        capped = score_0_100
    return _clamp(capped)


def normalise_forex_reserves(months_import_cover: float) -> float:
    """
    Forex reserves in months of import cover → pressure score 0–100.

    Inverted scale: more reserves = lower pressure.
    IMF adequacy thresholds for Kenya used as anchor points:
      ≥ 8 months  → 0    (very comfortable buffer)
        6 months  → 15
        4.5 months→ 35   (CBK target floor)
        4 months  → 50   (IMF minimum guidance)
        3 months  → 70
        2 months  → 88
      ≤ 1 month   → 100  (acute crisis)
    """
    bp = [
        (1.0,  100.0),
        (2.0,   88.0),
        (3.0,   70.0),
        (4.0,   50.0),
        (4.5,   35.0),
        (6.0,   15.0),
        (8.0,    0.0),
    ]
    return _clamp(_piecewise_linear(months_import_cover, bp))


def normalise_eurobond_spread(spread_pp: float) -> float:
    """
    Kenya Eurobond sovereign spread above US 10yr Treasury (percentage points)
    → pressure score 0–100.

    A wider spread = higher investor risk premium = more stress.
    Breakpoints calibrated to Kenya's historical spread range:
      ≤ 2 pp  → 0    (excellent credit perception)
        4 pp  → 20   (normal / pre-2020 baseline)
        6 pp  → 45   (elevated but manageable)
        8 pp  → 65   (high — IMF / market concern)
       10 pp  → 85   (severe — Eurobond rollover risk)
      ≥ 14 pp → 100  (crisis — near-default pricing)
    """
    bp = [
        (0.0,   0.0),
        (2.0,   0.0),
        (4.0,  20.0),
        (6.0,  45.0),
        (8.0,  65.0),
        (10.0, 85.0),
        (14.0, 100.0),
    ]
    return _clamp(_piecewise_linear(spread_pp, bp))


def normalise_mpesa_volume(yoy_growth_pct: float) -> float:
    """
    M-Pesa / mobile money transaction value YoY growth (%) → pressure score 0–100.

    Inverted scale: strong growth = low pressure; contraction = high pressure.
    Kenya's mobile money growth has averaged ~15–25% YoY over 2015–2023.
      ≥ 20 % YoY → 0    (vibrant economic activity)
        15 %     → 8
        10 %     → 20
         5 %     → 40
         0 %     → 62   (stagnation — nominal growth = inflation erosion)
        -5 %     → 80
      ≤ -10 %    → 100  (sharp contraction)
    """
    bp = [
        (-10.0, 100.0),
        ( -5.0,  80.0),
        (  0.0,  62.0),
        (  5.0,  40.0),
        ( 10.0,  20.0),
        ( 15.0,   8.0),
        ( 20.0,   0.0),
    ]
    return _clamp(_piecewise_linear(yoy_growth_pct, bp))
