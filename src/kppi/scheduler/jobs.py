"""
Scheduled background jobs using APScheduler.

The scheduler runs the full data-collection + index-computation cycle
at a configurable interval (default: every 24 hours).

Usage::

    from kppi.scheduler.jobs import start_scheduler, run_once
    run_once()          # immediate one-shot execution
    start_scheduler()   # blocks; runs periodically
"""
from __future__ import annotations

import sys
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger

from kppi.config import settings
from kppi.data.pipeline import DataPipeline
from kppi.index.calculator import KPPICalculator
from kppi.storage.database import Database
from kppi.notifications import send_kppi_email


def run_once(db: Database | None = None) -> None:
    """
    Execute a single full cycle:
      1. Fetch all indicators via the data pipeline
      2. Compute the KPPI composite score
      3. Persist the result to the database
      4. Send email summary (if EMAIL_ENABLED=true)
    """
    db = db or Database()
    pipeline = DataPipeline(db=db)
    calculator = KPPICalculator()

    logger.info("── KPPI update cycle started at {} ──", datetime.utcnow().isoformat())

    try:
        snapshot = pipeline.run()
        result = calculator.compute(snapshot)

        # ── 4-week political moving average ────────────────────────────────
        # Pull last 3 stored raw_political values (oldest first), append
        # the current reading, then average all available points.
        prior = db.recent_political_raw(n=3)
        if result.raw_political is not None and prior:
            window = prior + [result.raw_political]
            result.political_smoothed = round(sum(window) / len(window), 2)
            logger.debug(
                "Political MA-{}w: {} → {:.1f}",
                len(window), [f"{v:.1f}" for v in window], result.political_smoothed,
            )

        row_id = db.save_result(result)
        logger.success(
            "KPPI update complete: score={} tier={} db_id={}",
            result.composite_score, result.tier, row_id,
        )
        send_kppi_email(result)
    except Exception as exc:
        logger.error("KPPI update cycle failed: {}", exc)
        raise


def start_scheduler(blocking: bool = True) -> BlockingScheduler | BackgroundScheduler:
    """
    Start the APScheduler-based periodic job.

    Parameters
    ----------
    blocking:
        If True (default), uses `BlockingScheduler` and blocks the calling
        thread.  Pass False for embedding in an async app (returns the
        running `BackgroundScheduler`).
    """
    interval_hours = settings.update_interval_hours
    db = Database()

    # Run immediately on start-up, then on the interval
    run_once(db)

    SchedulerClass = BlockingScheduler if blocking else BackgroundScheduler
    scheduler = SchedulerClass(timezone="UTC")

    scheduler.add_job(
        func=run_once,
        trigger=IntervalTrigger(hours=interval_hours),
        kwargs={"db": db},
        id="kppi_update",
        name="KPPI daily update",
        replace_existing=True,
        misfire_grace_time=3600,  # allow 1 h late-fire window
    )

    logger.info(
        "Scheduler started: next run in {} hour(s). Press Ctrl+C to stop.",
        interval_hours,
    )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped by user")
        scheduler.shutdown(wait=False)

    return scheduler
