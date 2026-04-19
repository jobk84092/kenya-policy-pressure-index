"""
Kenya Policy Pressure Index – Streamlit Dashboard

Run with:
    streamlit run src/kppi/dashboard/app.py

Or via the project CLI:
    python run.py dashboard
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure the package is importable when launched directly via `streamlit run`
_src = Path(__file__).resolve().parent.parent.parent
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
from loguru import logger

from kppi.config import settings
from kppi.data.pipeline import DataPipeline
from kppi.index.calculator import KPPICalculator, TIER_LABELS
from kppi.storage.database import Database

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Kenya Policy Pressure Index",
    page_icon="🇰🇪",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .metric-box {
        background: #1e1e2e;
        border-radius: 10px;
        padding: 1rem;
        text-align: center;
    }
    .kppi-score {
        font-size: 3.5rem;
        font-weight: 800;
        line-height: 1;
    }
    .tier-label {
        font-size: 1.1rem;
        font-weight: 600;
        letter-spacing: 0.05em;
    }
    div[data-testid="stMetric"] label {
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
    }
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

@st.cache_resource
def get_database() -> Database:
    return Database()


@st.cache_data(ttl=300)  # refresh display data every 5 minutes
def load_history(days: int) -> pd.DataFrame:
    return get_database().load_history(days=days)


def _tier_colour(tier: str) -> str:
    colours = {
        "Low":      "#22c55e",
        "Moderate": "#eab308",
        "High":     "#f97316",
        "Severe":   "#ef4444",
        "Crisis":   "#dc2626",
    }
    return colours.get(tier, "#6b7280")


def _gauge_chart(score: float, tier: str) -> go.Figure:
    colour = _tier_colour(tier)
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=score,
        number={"font": {"size": 52, "color": colour}, "suffix": ""},
        title={"text": "KPPI Score", "font": {"size": 16}},
        gauge={
            "axis": {"range": [0, 100], "tickwidth": 1},
            "bar": {"color": colour, "thickness": 0.25},
            "bgcolor": "white",
            "steps": [
                {"range": [0,  30], "color": "#dcfce7"},
                {"range": [30, 50], "color": "#fef9c3"},
                {"range": [50, 70], "color": "#ffedd5"},
                {"range": [70, 85], "color": "#fee2e2"},
                {"range": [85, 100],"color": "#fca5a5"},
            ],
            "threshold": {
                "line": {"color": colour, "width": 4},
                "thickness": 0.75,
                "value": score,
            },
        },
    ))
    fig.update_layout(height=280, margin=dict(t=40, b=10, l=20, r=20))
    return fig


def _trend_chart(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()

    # Shaded tier regions
    region_colours = ["#dcfce7", "#fef9c3", "#ffedd5", "#fee2e2", "#fca5a5"]
    for i, (lo, hi, label, _, _) in enumerate(TIER_LABELS):
        fig.add_hrect(
            y0=lo, y1=min(hi, 100),
            fillcolor=region_colours[i],
            opacity=0.3,
            layer="below",
            line_width=0,
            annotation_text=label,
            annotation_position="right",
            annotation_font_size=10,
        )

    fig.add_trace(go.Scatter(
        x=df["timestamp"],
        y=df["composite_score"],
        mode="lines+markers",
        name="KPPI",
        line=dict(color="#3b82f6", width=2.5),
        marker=dict(size=5),
        hovertemplate="<b>%{x|%Y-%m-%d}</b><br>KPPI: %{y:.1f}<extra></extra>",
    ))

    fig.update_layout(
        title="KPPI Trend",
        xaxis_title="Date",
        yaxis_title="Score (0–100)",
        yaxis=dict(range=[0, 105]),
        height=380,
        showlegend=False,
        margin=dict(t=50, b=40, l=50, r=120),
    )
    return fig


def _component_chart(latest: dict) -> go.Figure:
    labels = ["Inflation", "FX Rate", "Bond Yield", "Market Stress", "Political"]
    scores = [
        latest.get("score_inflation",  0),
        latest.get("score_fx_rate",    0),
        latest.get("score_bond_yield", 0),
        latest.get("score_market_stress", 0),
        latest.get("score_political",  0),
    ]
    colours = [
        _tier_colour("Low") if s < 30 else
        _tier_colour("Moderate") if s < 50 else
        _tier_colour("High") if s < 70 else
        _tier_colour("Severe") if s < 85 else
        _tier_colour("Crisis")
        for s in scores
    ]
    fig = go.Figure(go.Bar(
        x=scores,
        y=labels,
        orientation="h",
        marker_color=colours,
        text=[f"{s:.1f}" for s in scores],
        textposition="outside",
        hovertemplate="%{y}: %{x:.1f}<extra></extra>",
    ))
    fig.update_layout(
        title="Component Scores (0–100)",
        xaxis=dict(range=[0, 115], title="Pressure Score"),
        height=300,
        margin=dict(t=50, b=30, l=100, r=60),
    )
    return fig


def _radar_chart(latest: dict) -> go.Figure:
    categories = ["Inflation", "FX Rate", "Bond Yield", "Market Stress", "Political"]
    scores = [
        latest.get("score_inflation",  0),
        latest.get("score_fx_rate",    0),
        latest.get("score_bond_yield", 0),
        latest.get("score_market_stress", 0),
        latest.get("score_political",  0),
    ]
    # Close the polygon
    categories += [categories[0]]
    scores += [scores[0]]

    fig = go.Figure(go.Scatterpolar(
        r=scores,
        theta=categories,
        fill="toself",
        fillcolor="rgba(59, 130, 246, 0.25)",
        line=dict(color="#3b82f6", width=2),
    ))
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
        title="Component Radar",
        height=360,
        margin=dict(t=60, b=20, l=20, r=20),
    )
    return fig


def _component_history(df: pd.DataFrame) -> go.Figure:
    components = {
        "Inflation":   "score_inflation",
        "FX Rate":     "score_fx_rate",
        "Bond Yield":  "score_bond_yield",
        "Market Stress":  "score_market_stress",
        "Political":   "score_political",
    }
    fig = go.Figure()
    colours = ["#ef4444", "#f97316", "#eab308", "#22c55e", "#3b82f6"]
    for (label, col), colour in zip(components.items(), colours):
        if col in df.columns:
            fig.add_trace(go.Scatter(
                x=df["timestamp"],
                y=df[col],
                name=label,
                mode="lines",
                line=dict(width=1.8, color=colour),
                hovertemplate=f"<b>{label}</b><br>%{{x|%Y-%m-%d}}: %{{y:.1f}}<extra></extra>",
            ))
    fig.update_layout(
        title="Component Score History",
        xaxis_title="Date",
        yaxis_title="Score (0–100)",
        yaxis=dict(range=[0, 110]),
        height=380,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(t=80, b=40, l=50, r=20),
    )
    return fig


# ── Sidebar ───────────────────────────────────────────────────────────────────

def sidebar() -> tuple[int, bool]:
    st.sidebar.image(
        "https://upload.wikimedia.org/wikipedia/commons/4/49/Flag_of_Kenya.svg",
        width=80,
    )
    st.sidebar.title("🇰🇪 KPPI")
    st.sidebar.caption(settings.app_name + f" v{settings.app_version}")
    st.sidebar.divider()

    days = st.sidebar.slider("History window (days)", 7, 365, 90, step=7)

    st.sidebar.divider()
    st.sidebar.markdown("**Data mode**")
    use_mock = st.sidebar.checkbox(
        "Demo / mock data",
        value=settings.use_mock_data,
        help="Use synthetic data instead of live API calls",
    )

    st.sidebar.divider()
    st.sidebar.markdown("**Index weights**")
    st.sidebar.markdown(f"""
| Component | Weight |
|-----------|--------|
| Inflation | {settings.weight_inflation:.0%} |
| FX Rate | {settings.weight_fx:.0%} |
| Bond Yield | {settings.weight_bond:.0%} |
| Market Stress | {settings.weight_market_stress:.0%} |
| Political | {settings.weight_political:.0%} |
""")

    st.sidebar.divider()
    st.sidebar.caption(
        "Sources: World Bank, Open ExchangeRate API, GDELT Project. "
        "Market stress uses free public macro proxies."
    )
    return days, use_mock


# ── Main app ──────────────────────────────────────────────────────────────────

def main() -> None:
    days, use_mock = sidebar()

    st.title("🇰🇪 Kenya Policy Pressure Index")
    st.caption(
        "A composite indicator measuring political-economic stress in Kenya "
        "across inflation, currency, bond markets, market stress and political events."
    )

    db = get_database()
    df = load_history(days)

    # ── Header: current / latest score ────────────────────────────────────────
    col_refresh, _ = st.columns([1, 5])
    with col_refresh:
        refresh = st.button("🔄 Refresh Now", use_container_width=True)

    if refresh:
        with st.spinner("Fetching latest data…"):
            import os
            if use_mock:
                os.environ["USE_MOCK_DATA"] = "true"
            from kppi.scheduler.jobs import run_once
            run_once(db)
            st.cache_data.clear()
            df = load_history(days)
        st.success("Data refreshed!")

    if df.empty:
        st.info(
            "No data yet.  Click **Refresh Now** to run the first data collection."
        )
        return

    latest = df.iloc[-1].to_dict()
    score  = latest["composite_score"]
    tier   = latest["tier"]
    ts     = pd.to_datetime(latest["timestamp"]).strftime("%d %b %Y %H:%M UTC")

    # ── KPI row ───────────────────────────────────────────────────────────────
    st.divider()
    kpi_cols = st.columns([2, 1, 1, 1, 1, 1])

    with kpi_cols[0]:
        st.plotly_chart(_gauge_chart(score, tier), use_container_width=True)

    kpi_defs = [
        ("Inflation",  "raw_inflation",  "% YoY"),
        ("FX Rate",    "raw_fx_rate",    "KES/USD"),
        ("Bond Yield", "raw_bond_yield", "%"),
        ("Political",  "raw_political",  "/ 100"),
    ]
    for i, (label, key, unit) in enumerate(kpi_defs, start=1):
        raw = latest.get(key)
        with kpi_cols[i]:
            st.metric(
                label=label,
                value=f"{raw:.1f} {unit}" if raw is not None else "N/A",
            )

    st.caption(f"Last updated: {ts}  |  {len(df)} readings in window")
    st.divider()

    # ── Trend + radar row ─────────────────────────────────────────────────────
    trend_col, radar_col = st.columns([3, 2])

    with trend_col:
        st.plotly_chart(_trend_chart(df), use_container_width=True)

    with radar_col:
        st.plotly_chart(_radar_chart(latest), use_container_width=True)

    # ── Component bar + history row ───────────────────────────────────────────
    bar_col, hist_col = st.columns([2, 3])

    with bar_col:
        st.plotly_chart(_component_chart(latest), use_container_width=True)

    with hist_col:
        if len(df) > 1:
            st.plotly_chart(_component_history(df), use_container_width=True)
        else:
            st.info("Run at least two updates to see component history.")

    # ── Data table ────────────────────────────────────────────────────────────
    with st.expander("📋 Raw data table"):
        display_cols = [
            "timestamp", "composite_score", "tier",
            "score_inflation", "score_fx_rate", "score_bond_yield",
            "score_market_stress", "score_political",
            "raw_inflation", "raw_fx_rate", "raw_bond_yield", "raw_market_stress", "raw_political",
        ]
        existing = [c for c in display_cols if c in df.columns]
        st.dataframe(
            df[existing].sort_values("timestamp", ascending=False),
            use_container_width=True,
        )

        csv = df[existing].to_csv(index=False).encode("utf-8")
        st.download_button(
            label="⬇ Download CSV",
            data=csv,
            file_name="kppi_history.csv",
            mime="text/csv",
        )

    # ── Methodology note ──────────────────────────────────────────────────────
    with st.expander("ℹ️ Methodology"):
        st.markdown("""
### KPPI Methodology

The **Kenya Policy Pressure Index (KPPI)** is a weighted composite of five
normalised pressure indicators.  Each sub-indicator is mapped to a 0–100
scale where **0 = no stress** and **100 = crisis-level stress**.

| Component | Weight | Source | Notes |
|-----------|--------|--------|-------|
| Inflation | 25 % | World Bank / KNBS | Annual CPI % YoY |
| FX Rate | 20 % | Open ExchangeRate API | KES depreciation vs USD |
| Bond Yield | 20 % | World Bank T-bill | Proxy for fiscal risk premium |
| Market Stress | 15 % | World Bank + FX + regional proxy | Composite stress score |
| Political Events | 20 % | GDELT Project | News volume + sentiment |

#### Pressure Tiers
| Score | Tier | Interpretation |
|-------|------|----------------|
| 0–30 | 🟢 Low | Stable – no significant stress signals |
| 30–50 | 🟡 Moderate | Watch – some economic or political headwinds |
| 50–70 | 🟠 High | Elevated – material stress, monitor closely |
| 70–85 | 🔴 Severe | Severe – multiple stress factors compounding |
| 85–100 | 🚨 Crisis | Acute instability across indicators |

> **Disclaimer**: KPPI is a research/learning tool.  It is not financial advice.
> Data freshness depends on API update cadences (World Bank lags by ~1 year for
> annual indicators).
""")


if __name__ == "__main__":
    main()
