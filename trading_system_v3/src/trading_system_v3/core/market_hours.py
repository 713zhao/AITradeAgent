"""US equity market-hours gate (naive, no holiday calendar -- matches the
baseline's scope; `--bypass-market-hours` skips this for testing/backtests)."""
from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

_EASTERN = ZoneInfo("America/New_York")
_OPEN = time(9, 30)
_CLOSE = time(16, 0)


def is_market_open(now: datetime | None = None) -> bool:
    now = (now or datetime.now(_EASTERN)).astimezone(_EASTERN)
    if now.weekday() >= 5:
        return False
    return _OPEN <= now.time() <= _CLOSE
