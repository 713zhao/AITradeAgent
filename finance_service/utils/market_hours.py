"""Utility functions for market hours checking."""
from datetime import datetime
from zoneinfo import ZoneInfo

def is_us_market_open() -> bool:
    """Check if US markets (NYSE/NASDAQ) are currently open."""
    now = datetime.now(ZoneInfo("America/New_York"))
    # Weekends
    if now.weekday() >= 5:
        return False
    # Market hours 9:30 AM - 4:00 PM ET
    opening = now.replace(hour=9, minute=30, second=0, microsecond=0)
    closing = now.replace(hour=16, minute=0, second=0, microsecond=0)
    return opening <= now <= closing

def is_hk_market_open() -> bool:
    """Check if Hong Kong market is currently open."""
    now = datetime.now(ZoneInfo("Asia/Hong_Kong"))
    # Weekends
    if now.weekday() >= 5:
        return False
    # Market hours 9:30 AM - 4:00 PM HKT
    opening = now.replace(hour=9, minute=30, second=0, microsecond=0)
    closing = now.replace(hour=16, minute=0, second=0, microsecond=0)
    return opening <= now <= closing
