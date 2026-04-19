"""
SQLite persistence layer for KPPI results.

Schema
------
  kppi_readings   – one row per KPPI computation (composite + components + raws)
  raw_indicators  – one row per raw indicator fetch (for audit / replay)

Uses only the stdlib `sqlite3` module – no ORM required at this scale.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator, Optional

import pandas as pd
from loguru import logger

from kppi.config import settings
from kppi.index.calculator import KPPIResult


# ── DDL ───────────────────────────────────────────────────────────────────────

_CREATE_KPPI_READINGS = """
CREATE TABLE IF NOT EXISTS kppi_readings (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp         TEXT    NOT NULL UNIQUE,
    composite_score   REAL    NOT NULL,
    tier              TEXT    NOT NULL,
    confidence_score  REAL,
    confidence_label  TEXT,
    confidence_notes  TEXT,

    -- Normalised component scores (0–100)
    score_inflation   REAL,
    score_fx_rate     REAL,
    score_bond_yield  REAL,
    score_market_stress REAL,
    score_political   REAL,

    -- Raw indicator values
    raw_inflation     REAL,
    raw_fx_rate       REAL,
    raw_bond_yield    REAL,
    raw_market_stress REAL,
    raw_political     REAL,
    -- Smoothed political (4-week moving average, computed in jobs.py)
    political_smoothed REAL
);
"""

_CREATE_RAW_INDICATORS = """
CREATE TABLE IF NOT EXISTS raw_indicators (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT    NOT NULL,
    name        TEXT    NOT NULL,
    value       REAL    NOT NULL,
    unit        TEXT,
    source      TEXT,
    notes       TEXT
);
"""

_CREATE_IDX_TIMESTAMP = """
CREATE INDEX IF NOT EXISTS idx_kppi_timestamp ON kppi_readings(timestamp);
"""


# ── Database manager ──────────────────────────────────────────────────────────

class Database:
    """
    Thread-safe (check_same_thread=False) SQLite wrapper.

    Usage::

        db = Database()
        db.save_result(result)
        df = db.load_history(days=90)
    """

    def __init__(self, db_path: Optional[str | Path] = None) -> None:
        self._path = Path(db_path or settings.db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._initialise()

    # ── Internal helpers ──────────────────────────────────────────────────────

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager yielding an auto-committing connection."""
        conn = sqlite3.connect(self._path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _initialise(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                _CREATE_KPPI_READINGS
                + _CREATE_RAW_INDICATORS
                + _CREATE_IDX_TIMESTAMP
            )
            # Schema migration: add market_stress columns if they don't exist yet
            # (handles DBs created before the NSE → market_stress refactor)
            existing = {
                row[1]
                for row in conn.execute("PRAGMA table_info(kppi_readings)").fetchall()
            }
            for col, col_type in (
                ("score_market_stress", "REAL"),
                ("raw_market_stress", "REAL"),
                ("confidence_score", "REAL"),
                ("confidence_label", "TEXT"),
                ("confidence_notes", "TEXT"),
                ("political_smoothed", "REAL"),
            ):
                if col not in existing:
                    conn.execute(
                        f"ALTER TABLE kppi_readings ADD COLUMN {col} {col_type}"
                    )
                    logger.info("DB migration: added column {}", col)
        logger.debug("Database initialised at {}", self._path)

    # ── Write operations ──────────────────────────────────────────────────────

    def save_result(self, result: KPPIResult) -> int:
        """
        Persist a KPPIResult.  Returns the new row id.
        Silently skips duplicate timestamps (same-second re-runs).
        """
        sql = """
        INSERT OR IGNORE INTO kppi_readings (
            timestamp, composite_score, tier, confidence_score, confidence_label, confidence_notes,
            score_inflation, score_fx_rate, score_bond_yield, score_market_stress, score_political,
            raw_inflation, raw_fx_rate, raw_bond_yield, raw_market_stress, raw_political,
            political_smoothed
        ) VALUES (
            :timestamp, :composite_score, :tier, :confidence_score, :confidence_label, :confidence_notes,
            :score_inflation, :score_fx_rate, :score_bond_yield, :score_market_stress, :score_political,
            :raw_inflation, :raw_fx_rate, :raw_bond_yield, :raw_market_stress, :raw_political,
            :political_smoothed
        )
        """
        row = result.as_dict()
        with self._conn() as conn:
            cursor = conn.execute(sql, row)
            row_id = cursor.lastrowid or 0

        if row_id:
            logger.debug("Saved KPPIResult id={} score={}", row_id, result.composite_score)
        else:
            logger.debug("Duplicate timestamp skipped: {}", result.timestamp.isoformat())
        return row_id

    # ── Read operations ───────────────────────────────────────────────────────

    def load_history(self, days: int = 365) -> pd.DataFrame:
        """
        Return a DataFrame of KPPI readings for the past `days` days,
        ordered chronologically.
        """
        sql = """
        SELECT * FROM kppi_readings
        WHERE timestamp >= datetime('now', :offset)
        ORDER BY timestamp ASC
        """
        with self._conn() as conn:
            rows = conn.execute(sql, {"offset": f"-{days} days"}).fetchall()

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame([dict(r) for r in rows])
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        return df

    def latest_result(self) -> Optional[dict]:
        """Return the most recent KPPI reading as a dict, or None."""
        sql = "SELECT * FROM kppi_readings ORDER BY timestamp DESC LIMIT 1"
        with self._conn() as conn:
            row = conn.execute(sql).fetchone()
        return dict(row) if row else None

    def record_count(self) -> int:
        with self._conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM kppi_readings").fetchone()[0]

    def export_csv(self, output_path: str | Path) -> Path:
        """Export full history to CSV and return the path."""
        df = self.load_history(days=9999)
        out = Path(output_path)
        df.to_csv(out, index=False)
        logger.info("Exported {} rows to {}", len(df), out)
        return out

    def recent_political_raw(self, n: int = 4) -> list[float]:
        """Return up to `n` most recent non-null raw_political values (oldest first)."""
        sql = """
        SELECT raw_political FROM kppi_readings
        WHERE raw_political IS NOT NULL
        ORDER BY timestamp DESC
        LIMIT :n
        """
        with self._conn() as conn:
            rows = conn.execute(sql, {"n": n}).fetchall()
        return [row[0] for row in reversed(rows)]
