"""
Tests for the SQLite storage layer.
Uses a temporary in-memory database for isolation.
"""
from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from kppi.data.fetchers.base import IndicatorReading
from kppi.data.pipeline import RawSnapshot
from kppi.index.calculator import KPPICalculator
from kppi.storage.database import Database


def _make_result(score_offset: float = 0.0):
    snap = RawSnapshot(
        inflation=IndicatorReading("inflation", 6.5 + score_offset, "pct", "test"),
        fx_rate=IndicatorReading("fx_rate", 148.5, "KES_per_USD", "test"),
        bond_yield=IndicatorReading("bond_yield", 16.0, "pct", "test"),
        market_stress=IndicatorReading("market_stress", 45.0, "score_0_100", "test"),
        political_pressure=IndicatorReading("political_pressure", 45.0, "score", "test"),
        fetched_at=datetime.utcnow(),
    )
    return KPPICalculator().compute(snap)


@pytest.fixture
def db(tmp_path: Path) -> Database:
    """Fresh database in a temp directory for each test."""
    return Database(db_path=str(tmp_path / "test_kppi.db"))


class TestDatabase:
    def test_save_and_count(self, db: Database):
        result = _make_result()
        db.save_result(result)
        assert db.record_count() == 1

    def test_multiple_saves(self, db: Database):
        for i in range(5):
            import time; time.sleep(0.01)  # ensure distinct timestamps
            db.save_result(_make_result(score_offset=float(i)))
        assert db.record_count() == 5

    def test_load_history_returns_dataframe(self, db: Database):
        db.save_result(_make_result())
        df = db.load_history(days=365)
        assert not df.empty
        assert "composite_score" in df.columns

    def test_load_history_empty_on_fresh_db(self, db: Database):
        df = db.load_history(days=365)
        assert df.empty

    def test_latest_result_returns_dict(self, db: Database):
        db.save_result(_make_result())
        latest = db.latest_result()
        assert latest is not None
        assert "composite_score" in latest

    def test_latest_result_none_on_empty_db(self, db: Database):
        assert db.latest_result() is None

    def test_export_csv(self, db: Database, tmp_path: Path):
        db.save_result(_make_result())
        out = tmp_path / "export.csv"
        db.export_csv(out)
        assert out.exists()
        assert out.stat().st_size > 0

    def test_duplicate_timestamp_ignored(self, db: Database):
        from datetime import timezone
        fixed_ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = _make_result()
        result.timestamp = fixed_ts
        db.save_result(result)
        result2 = _make_result()
        result2.timestamp = fixed_ts  # same timestamp → second insert ignored
        db.save_result(result2)
        assert db.record_count() == 1

    def test_history_columns_present(self, db: Database):
        db.save_result(_make_result())
        df = db.load_history()
        for col in ("timestamp", "composite_score", "tier", "score_inflation"):
            assert col in df.columns, f"Column {col!r} missing from history DataFrame"
