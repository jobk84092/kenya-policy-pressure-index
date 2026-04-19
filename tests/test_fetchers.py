"""
Tests for individual data fetchers.

Live HTTP calls are intercepted by the `responses` library so tests run
offline without any API keys.
"""
from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import patch

import pytest
import responses as resp_mock

from kppi.data.fetchers.base import IndicatorReading
from kppi.data.fetchers.exchangerate import FXRateFetcher
from kppi.data.fetchers.worldbank import InflationFetcher, TBillRateFetcher
from kppi.data.fetchers.nasi import NASIFetcher, _CATEGORY_URL
from kppi.data.fetchers.mock import (
    MockInflationFetcher,
    MockFXRateFetcher,
    MockBondYieldFetcher,
    MockMarketStressFetcher,
    MockPoliticalFetcher,
)

# ── Mock fetchers (no network) ────────────────────────────────────────────────

class TestMockFetchers:
    def test_mock_inflation_returns_reading(self):
        r = MockInflationFetcher().fetch()
        assert isinstance(r, IndicatorReading)
        assert r.name == "inflation"
        assert 0 < r.value < 50

    def test_mock_fx_returns_reading(self):
        r = MockFXRateFetcher().fetch()
        assert r.name == "fx_rate"
        assert r.value > 0

    def test_mock_bond_returns_reading(self):
        r = MockBondYieldFetcher().fetch()
        assert r.name == "bond_yield"
        assert r.value > 0

    def test_mock_market_stress_returns_nasi_scale(self):
        r = MockMarketStressFetcher().fetch()
        assert r.name == "market_stress"
        # Mock now returns NASI-scale value (~162), not a 0-100 score
        assert r.value > 100, "Mock market stress should return NASI index level (>100)"
        assert r.unit == "nasi_index_level"

    def test_mock_political_returns_reading(self):
        r = MockPoliticalFetcher().fetch()
        assert r.name == "political_pressure"
        assert 0 <= r.value <= 100

    def test_mock_all_have_source_tag(self):
        fetchers = [
            MockInflationFetcher(),
            MockFXRateFetcher(),
            MockBondYieldFetcher(),
            MockMarketStressFetcher(),
            MockPoliticalFetcher(),
        ]
        for fetcher in fetchers:
            r = fetcher.fetch()
            assert r.source == "mock", f"{type(fetcher).__name__} has wrong source"


# ── NASI fetcher ──────────────────────────────────────────────────────────────

class TestNASIFetcher:
    _TITLE_WITH_VALUE = (
        "Kenyan Market Snapshot: April 17, 2026 — NASI slips 0.8% to 176.45"
    )
    _TITLE_NO_VALUE = (
        "NSE Weekly Wrap: NASI Gains 1.8% as Banking Stocks Rally"
    )

    def _make_html(self, title: str) -> str:
        return (
            "<html><body>"
            f'<h2><a href="/blog/2026-04-17-kenyan-market-snapshot">{title}</a></h2>'
            "</body></html>"
        )

    @resp_mock.activate
    def test_extracts_nasi_value_from_title(self):
        resp_mock.add(
            resp_mock.GET,
            _CATEGORY_URL,
            body=self._make_html(self._TITLE_WITH_VALUE),
            status=200,
            content_type="text/html",
        )
        r = NASIFetcher().fetch()
        assert r.name == "market_stress"
        assert r.value == 176.45
        assert r.unit == "nasi_index_level"
        assert r.source == "nseinsider.co.ke"

    @resp_mock.activate
    def test_raises_when_no_absolute_value(self):
        resp_mock.add(
            resp_mock.GET,
            _CATEGORY_URL,
            body=self._make_html(self._TITLE_NO_VALUE),
            status=200,
            content_type="text/html",
        )
        with pytest.raises(ValueError, match="No absolute NASI"):
            NASIFetcher().fetch()

    @resp_mock.activate
    def test_safe_fetch_returns_none_on_http_error(self):
        resp_mock.add(resp_mock.GET, _CATEGORY_URL, status=503)
        result = NASIFetcher().safe_fetch()
        assert result is None

    @resp_mock.activate
    def test_handles_value_with_decimal(self):
        html = self._make_html(
            "Kenyan Market Snapshot: April 14, 2026 — NASI dips 0.4% to 178.9 amid mixed sentiment"
        )
        resp_mock.add(
            resp_mock.GET,
            _CATEGORY_URL,
            body=html,
            status=200,
            content_type="text/html",
        )
        r = NASIFetcher().fetch()
        assert r.value == 178.9


# ── World Bank fetcher ────────────────────────────────────────────────────────

class TestWorldBankInflationFetcher:
    _SAMPLE_RESPONSE = [
        {"page": 1, "pages": 1, "per_page": 5, "total": 5},
        [
            {"indicator": {"id": "FP.CPI.TOTL.ZG"}, "country": {"id": "KE"},
             "date": "2023", "value": 7.8},
            {"indicator": {"id": "FP.CPI.TOTL.ZG"}, "country": {"id": "KE"},
             "date": "2022", "value": None},
        ],
    ]

    @resp_mock.activate
    def test_fetches_most_recent_non_null(self):
        resp_mock.add(
            resp_mock.GET,
            "https://api.worldbank.org/v2/country/KE/indicator/FP.CPI.TOTL.ZG",
            json=self._SAMPLE_RESPONSE,
            status=200,
        )
        reading = InflationFetcher().fetch()
        assert reading.value == 7.8
        assert reading.unit == "percent_yoy"

    @resp_mock.activate
    def test_raises_on_empty_response(self):
        resp_mock.add(
            resp_mock.GET,
            "https://api.worldbank.org/v2/country/KE/indicator/FP.CPI.TOTL.ZG",
            json=[{}, []],
            status=200,
        )
        with pytest.raises(ValueError):
            InflationFetcher().fetch()

    @resp_mock.activate
    def test_safe_fetch_returns_none_on_http_error(self):
        resp_mock.add(
            resp_mock.GET,
            "https://api.worldbank.org/v2/country/KE/indicator/FP.CPI.TOTL.ZG",
            status=500,
        )
        result = InflationFetcher().safe_fetch()
        assert result is None

    @resp_mock.activate
    def test_safe_fetch_returns_fallback_on_error(self):
        resp_mock.add(
            resp_mock.GET,
            "https://api.worldbank.org/v2/country/KE/indicator/FP.CPI.TOTL.ZG",
            status=503,
        )
        result = InflationFetcher().safe_fetch(fallback=5.0)
        assert result is not None
        assert result.value == 5.0
        assert result.source == "fallback"


# ── ExchangeRate fetcher ──────────────────────────────────────────────────────

class TestFXRateFetcher:
    _SAMPLE_RESPONSE = {
        "result": "success",
        "base_code": "USD",
        "rates": {"KES": 148.5, "EUR": 0.92, "GBP": 0.79},
    }

    @resp_mock.activate
    def test_fetches_kes_rate(self):
        resp_mock.add(
            resp_mock.GET,
            "https://open.er-api.com/v6/latest/USD",
            json=self._SAMPLE_RESPONSE,
            status=200,
        )
        reading = FXRateFetcher().fetch()
        assert reading.value == 148.5
        assert reading.unit == "KES_per_USD"

    @resp_mock.activate
    def test_raises_on_api_error_flag(self):
        resp_mock.add(
            resp_mock.GET,
            "https://open.er-api.com/v6/latest/USD",
            json={"result": "error", "error-type": "invalid-key"},
            status=200,
        )
        with pytest.raises(ValueError, match="ExchangeRate API error"):
            FXRateFetcher().fetch()

    @resp_mock.activate
    def test_raises_when_kes_missing(self):
        resp_mock.add(
            resp_mock.GET,
            "https://open.er-api.com/v6/latest/USD",
            json={"result": "success", "rates": {"EUR": 0.92}},
            status=200,
        )
        with pytest.raises(KeyError):
            FXRateFetcher().fetch()


# ── IndicatorReading validation ───────────────────────────────────────────────

class TestIndicatorReading:
    def test_rejects_non_numeric_value(self):
        with pytest.raises(TypeError):
            IndicatorReading(
                name="test", value="bad", unit="x", source="test"  # type: ignore[arg-type]
            )

    def test_accepts_integer_value(self):
        r = IndicatorReading(name="test", value=42, unit="x", source="test")
        assert r.value == 42

    def test_timestamp_defaults_to_now(self):
        before = datetime.utcnow()
        r = IndicatorReading(name="test", value=1.0, unit="x", source="test")
        assert r.timestamp >= before
