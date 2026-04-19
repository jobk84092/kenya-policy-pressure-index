"""
KPPI CLI / entrypoint.

Usage
-----
    python run.py                # one-shot: fetch + compute + save + print
    python run.py dashboard      # launch Streamlit dashboard
    python run.py schedule       # run once, then loop on interval
    python run.py export         # export history to CSV
"""
from __future__ import annotations

import sys
import subprocess
from pathlib import Path

# Make the src/ layout importable without installing the package
_src = Path(__file__).parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from loguru import logger
from kppi.config import settings
from kppi.storage.database import Database
from kppi.scheduler.jobs import run_once


def _setup_logging() -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        level="INFO",
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
    )
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    logger.add(
        log_dir / "kppi_{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="30 days",
        level="DEBUG",
        encoding="utf-8",
    )


def cmd_once() -> None:
    """Run a single fetch-compute-store cycle and print the result."""
    db = Database()
    run_once(db)
    latest = db.latest_result()
    if latest:
        score = latest["composite_score"]
        tier  = latest["tier"]
        print(f"\n{'═' * 45}")
        print(f"  Kenya Policy Pressure Index (KPPI)")
        print(f"{'═' * 45}")
        print(f"  Score : {score:.1f} / 100")
        print(f"  Tier  : {tier}")
        print(f"{'─' * 45}")
        print(f"  Inflation  : {latest.get('score_inflation', 'N/A'):.1f}")
        print(f"  FX Rate    : {latest.get('score_fx_rate', 'N/A'):.1f}")
        print(f"  Bond Yield : {latest.get('score_bond_yield', 'N/A'):.1f}")
        print(f"  Market Stress : {latest.get('score_market_stress', 'N/A'):.1f}")
        print(f"  Political  : {latest.get('score_political', 'N/A'):.1f}")
        print(f"{'═' * 45}\n")


def cmd_dashboard() -> None:
    """Launch the Streamlit dashboard."""
    app_path = Path(__file__).parent / "src" / "kppi" / "dashboard" / "app.py"
    logger.info("Launching dashboard: {}", app_path)
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", str(app_path)],
        check=True,
    )


def cmd_schedule() -> None:
    """Run once immediately, then on the configured interval."""
    from kppi.scheduler.jobs import start_scheduler
    start_scheduler(blocking=True)


def cmd_export() -> None:
    """Export full history to CSV."""
    db = Database()
    out = Path("data") / "kppi_export.csv"
    db.export_csv(out)
    print(f"Exported to {out.resolve()}")


def cmd_setup_weekly() -> None:
    """
    Install a macOS launchd plist that runs KPPI every Sunday at 08:00 local
    time, with email notification.

    After running this command:
      1. Make sure .env contains EMAIL_ENABLED=true and SMTP credentials.
      2. The job loads automatically at login and fires each Sunday.
      3. To uninstall: launchctl unload ~/Library/LaunchAgents/com.kppi.weekly.plist
    """
    import plistlib

    project_dir = Path(__file__).parent.resolve()
    # Use the venv python directly (not resolved) so site-packages are found
    venv_python = project_dir / ".venv" / "bin" / "python"
    python_bin  = venv_python if venv_python.exists() else Path(sys.executable).resolve()
    plist_dir   = Path.home() / "Library" / "LaunchAgents"
    plist_path  = plist_dir / "com.kppi.weekly.plist"
    log_dir     = project_dir / "logs"

    plist_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    plist_data = {
        "Label": "com.kppi.weekly",
        "ProgramArguments": [
            str(python_bin),
            str(project_dir / "run.py"),
            "once",
        ],
        "WorkingDirectory": str(project_dir),
        "EnvironmentVariables": {
            "USE_MOCK_DATA": "false",
        },
        "StartCalendarInterval": {
            "Weekday": 0,  # Sunday
            "Hour": 8,
            "Minute": 0,
        },
        "StandardOutPath": str(log_dir / "kppi_launchd.log"),
        "StandardErrorPath": str(log_dir / "kppi_launchd.log"),
        "RunAtLoad": False,
    }

    with open(plist_path, "wb") as f:
        plistlib.dump(plist_data, f)

    # Load into launchd
    result = subprocess.run(
        ["launchctl", "load", str(plist_path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"Warning: launchctl load returned: {result.stderr.strip()}")

    print(f"\n{'═' * 55}")
    print("  KPPI weekly job installed!")
    print(f"{'═' * 55}")
    print(f"  Runs    : Every Sunday at 08:00 local time")
    print(f"  Python  : {python_bin}")
    print(f"  Project : {project_dir}")
    print(f"  Log     : {log_dir / 'kppi_launchd.log'}")
    print(f"  Plist   : {plist_path}")
    print(f"{'─' * 55}")
    print("  Make sure .env has EMAIL_ENABLED=true and SMTP credentials.")
    print("  To uninstall:")
    print(f"    launchctl unload {plist_path}")
    print(f"{'═' * 55}\n")


COMMANDS = {
    "once":         cmd_once,
    "dashboard":    cmd_dashboard,
    "schedule":     cmd_schedule,
    "export":       cmd_export,
    "setup-weekly": cmd_setup_weekly,
}

if __name__ == "__main__":
    _setup_logging()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "once"
    if cmd not in COMMANDS:
        print(f"Unknown command '{cmd}'. Available: {', '.join(COMMANDS)}")
        sys.exit(1)
    COMMANDS[cmd]()
