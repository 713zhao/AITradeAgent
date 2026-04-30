#!/usr/bin/env python3
"""
Progress Monitor Daemon

Runs as a persistent background service (managed by systemd).
Calls heartbeat_report.py every 30 minutes while any market is open.
Sends one final closing report when market transitions from open -> closed.

Market coverage:
  - Hong Kong Stock Exchange: 09:30-16:00 HKT (Mon-Fri)
  - US NYSE / NASDAQ:         09:30-16:00 ET  (Mon-Fri)
"""
from __future__ import annotations
import os
import sys
import time
import json
import logging
import importlib.util
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# Paths
WORKSPACE          = Path("/home/eric/.openclaw/workspace/AITradeAgent")
STATE_FILE         = WORKSPACE / "memory" / "progress_daemon_state.json"
LOG_FILE           = Path("/tmp/progress_monitor.log")
MONITOR_SCRIPT     = WORKSPACE / "scripts" / "heartbeat_report.py"

# Timing
INTERVAL_SECONDS   = 30 * 60   # 30-min between reports while market is open
POLL_SECONDS       = 60         # How often we wake to re-check market state

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [progress-daemon] %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(LOG_FILE), mode="a"),
    ],
)
logger = logging.getLogger(__name__)


# Market hours ---------------------------------------------------------------

def is_hk_market_open() -> bool:
    now = datetime.now(ZoneInfo("Asia/Hong_Kong"))
    if now.weekday() >= 5:
        return False
    return now.replace(hour=9, minute=30, second=0, microsecond=0) \
        <= now <= \
        now.replace(hour=16, minute=0, second=0, microsecond=0)


def is_us_market_open() -> bool:
    now = datetime.now(ZoneInfo("America/New_York"))
    if now.weekday() >= 5:
        return False
    return now.replace(hour=9, minute=30, second=0, microsecond=0) \
        <= now <= \
        now.replace(hour=16, minute=0, second=0, microsecond=0)


def any_market_open() -> bool:
    return is_hk_market_open() or is_us_market_open()


def open_markets_label() -> str:
    parts = []
    if is_hk_market_open():
        parts.append("HK")
    if is_us_market_open():
        parts.append("US")
    return "/".join(parts) if parts else "none"


# State persistency ----------------------------------------------------------

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"last_report_ts": 0.0, "market_was_open": False, "closing_report_sent": False}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


# Load .env ------------------------------------------------------------------

def load_env(env_file: Path) -> None:
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = val.strip()


# Run progress monitor -------------------------------------------------------

def run_progress_report(label: str = "") -> bool:
    """Load and execute heartbeat_report.main() directly."""
    try:
        project_root = str(WORKSPACE)
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

        load_env(WORKSPACE / ".env")

        spec = importlib.util.spec_from_file_location("heartbeat_report", MONITOR_SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        tag = f" [{label}]" if label else ""
        logger.info(f"Sending progress report{tag} ...")
        mod.main()
        logger.info(f"Progress report{tag} done.")
        return True
    except Exception as exc:
        logger.error(f"heartbeat_report failed: {exc}", exc_info=True)
        return False


# Main daemon loop -----------------------------------------------------------

def main() -> None:
    logger.info("=== Progress Monitor Daemon starting ===")
    logger.info(f"  Interval : {INTERVAL_SECONDS // 60} min (while any market is open)")
    logger.info(f"  Poll     : {POLL_SECONDS} s")
    logger.info(f"  State    : {STATE_FILE}")
    logger.info(f"  Log      : {LOG_FILE}")

    while True:
        try:
            state = load_state()
            now_ts = time.time()
            market_open = any_market_open()

            if market_open:
                # Market just opened (transition from closed)
                if not state.get("market_was_open", False):
                    logger.info(f"Market opened. Active: {open_markets_label()}")
                    state["market_was_open"] = True
                    state["closing_report_sent"] = False
                    save_state(state)

                # Send report every 30 minutes
                seconds_since = now_ts - state.get("last_report_ts", 0.0)
                if seconds_since >= INTERVAL_SECONDS:
                    ok = run_progress_report(label=f"open/{open_markets_label()}")
                    if ok:
                        state["last_report_ts"] = now_ts
                        save_state(state)
                else:
                    mins_left = int((INTERVAL_SECONDS - seconds_since) / 60)
                    logger.debug(f"Market open ({open_markets_label()}). Next report in ~{mins_left} min.")

            else:
                # Market closed: send one end-of-day report on transition
                if state.get("market_was_open", False) and not state.get("closing_report_sent", False):
                    logger.info("Market just closed. Sending end-of-day report.")
                    ok = run_progress_report(label="EOD/market-close")
                    if ok:
                        state["market_was_open"] = False
                        state["closing_report_sent"] = True
                        state["last_report_ts"] = now_ts
                        save_state(state)
                else:
                    logger.debug("Market closed. No reports needed. Waiting...")

        except Exception as exc:
            logger.error(f"Daemon loop error: {exc}", exc_info=True)

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
