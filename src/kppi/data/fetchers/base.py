"""
Base classes and shared data models for all KPPI data fetchers.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import requests
from loguru import logger


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class IndicatorReading:
    """Represents a single fetched indicator value."""

    name: str
    value: float
    unit: str
    source: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    notes: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.value, (int, float)):
            raise TypeError(f"IndicatorReading.value must be numeric; got {type(self.value)}")


# ── HTTP helper ───────────────────────────────────────────────────────────────

_DEFAULT_TIMEOUT = 15  # seconds
_USER_AGENT = "KPPI-Index/2.0 (research; +github.com/kppi)"


def _get_json(url: str, params: Optional[dict] = None, timeout: int = _DEFAULT_TIMEOUT) -> dict:
    """Simple GET with sensible defaults; raises on non-2xx status."""
    headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
    resp = requests.get(url, params=params, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


# ── Base fetcher ──────────────────────────────────────────────────────────────

class BaseFetcher(ABC):
    """
    Abstract fetcher.  Concrete subclasses must implement `fetch()`.
    `safe_fetch()` wraps it with logging and an optional fallback value.
    """

    #: Maximum number of retries on transient HTTP errors
    _MAX_RETRIES: int = 3
    _RETRY_DELAY: float = 2.0  # seconds

    @abstractmethod
    def fetch(self) -> IndicatorReading:
        """Fetch the indicator from its source.  Raises on failure."""
        ...

    def safe_fetch(self, fallback: Optional[float] = None) -> Optional[IndicatorReading]:
        """
        Call `fetch()` with retry logic and structured logging.
        Returns None (or an IndicatorReading built from `fallback`) on
        persistent failure so the pipeline can degrade gracefully.
        """
        last_exc: Optional[Exception] = None
        for attempt in range(1, self._MAX_RETRIES + 1):
            try:
                reading = self.fetch()
                logger.debug(
                    "[{}] fetched value={} unit={} source={}",
                    self.__class__.__name__,
                    reading.value,
                    reading.unit,
                    reading.source,
                )
                return reading
            except requests.exceptions.Timeout as exc:
                logger.warning(
                    "[{}] attempt {}/{} timed out: {}",
                    self.__class__.__name__, attempt, self._MAX_RETRIES, exc,
                )
                last_exc = exc
            except requests.exceptions.HTTPError as exc:
                logger.warning(
                    "[{}] attempt {}/{} HTTP error: {}",
                    self.__class__.__name__, attempt, self._MAX_RETRIES, exc,
                )
                last_exc = exc
            except Exception as exc:
                logger.error(
                    "[{}] unexpected error on attempt {}/{}: {}",
                    self.__class__.__name__, attempt, self._MAX_RETRIES, exc,
                )
                last_exc = exc

            if attempt < self._MAX_RETRIES:
                time.sleep(self._RETRY_DELAY)

        logger.error(
            "[{}] all {} attempts failed; last error: {}",
            self.__class__.__name__, self._MAX_RETRIES, last_exc,
        )

        if fallback is not None:
            logger.warning("[{}] using fallback value={}", self.__class__.__name__, fallback)
            return IndicatorReading(
                name=self.__class__.__name__,
                value=fallback,
                unit="unknown",
                source="fallback",
                notes=f"Live fetch failed ({last_exc}); fallback applied.",
            )
        return None
