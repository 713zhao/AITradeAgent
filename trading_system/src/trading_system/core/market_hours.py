from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

_US_TZ = ZoneInfo("America/New_York")


def is_us_market_open(now: datetime | None = None) -> bool:
    now = (now or datetime.now(_US_TZ)).astimezone(_US_TZ)
    if now.weekday() >= 5:
        return False
    open_t, close_t = time(9, 30), time(16, 0)
    return open_t <= now.time() <= close_t
