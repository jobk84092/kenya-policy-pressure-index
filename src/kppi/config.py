"""
Centralised configuration via pydantic-settings.

All values can be overridden by environment variables or a `.env` file
placed in the project root.  See `.env.example` for reference.
"""
from __future__ import annotations

from pathlib import Path
from typing import Annotated

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ───────────────────────────────────────────────────────────
    app_name: str = "Kenya Policy Pressure Index"
    app_version: str = "2.0.0"

    # ── Data mode ─────────────────────────────────────────────────────────────
    use_mock_data: bool = False

    # ── API keys ──────────────────────────────────────────────────────────────
    exchangerate_api_key: str = ""

    # ── Storage ───────────────────────────────────────────────────────────────
    db_path: str = "data/kppi.db"

    # ── Scheduling ────────────────────────────────────────────────────────────
    update_interval_hours: int = 168  # default: weekly

    # ── Email / SMTP ──────────────────────────────────────────────────────────
    email_enabled: bool = False
    email_to: str = ""
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""          # your Gmail address
    smtp_password: str = ""      # Gmail App Password (not your login password)

    # ── Index weights ─────────────────────────────────────────────────────────
    weight_inflation: float = 0.25
    weight_fx: float = 0.20
    weight_bond: float = 0.20
    weight_market_stress: float = 0.15
    weight_political: float = 0.20

    # ── Normalisation baselines ───────────────────────────────────────────────
    inflation_baseline: float = 5.0    # % YoY – "normal" Kenyan inflation
    fx_baseline: float = 110.0         # KES per USD – stable reference
    bond_yield_baseline: float = 12.0  # 10-yr government bond yield %
    nasi_baseline: float = 160.0       # NASI level – long-run calm reference
    # ── Derived properties ────────────────────────────────────────────────────
    @property
    def db_path_resolved(self) -> Path:
        return Path(self.db_path)

    @model_validator(mode="after")
    def _check_weights_sum(self) -> "Settings":
        total = (
            self.weight_inflation
            + self.weight_fx
            + self.weight_bond
            + self.weight_market_stress
            + self.weight_political
        )
        if abs(total - 1.0) > 1e-6:
            raise ValueError(
                f"Index weights must sum to 1.0; got {total:.4f}. "
                "Check WEIGHT_* environment variables."
            )
        return self

    @field_validator("update_interval_hours")
    @classmethod
    def _positive_interval(cls, v: int) -> int:
        if v < 1:
            raise ValueError("UPDATE_INTERVAL_HOURS must be >= 1")
        return v


# Module-level singleton – import and use directly.
settings = Settings()
