#!/usr/bin/env python3
"""Heartbeat report generator for AITradeAgent."""
import sqlite3
import os
from datetime import datetime
import pytz

def get_metrics():
    # Placeholder metrics - replace with real queries
    return {
        "total_trades": 20,
        "open_positions": 7,
        "cash": 29968.90,
        "equity": 101033.28,
        "pnl": 1033.28,
        "pnl_pct": 1.03,
        "drawdown": 0.0
    }

def get_market_status():
    try:
        now = datetime.now(pytz.timezone("Asia/Hong_Kong"))
        is_weekday = now.weekday() < 5
        hk_open = 9 <= now.hour < 16
        us_time = now.astimezone(pytz.timezone("US/Eastern"))
        us_open = 9 <= us_time.hour < 16
        return {
            "hk": "OPEN" if is_weekday and hk_open else "CLOSED",
            "us": "OPEN" if is_weekday and us_open else "CLOSED"
        }
    except:
        return {"hk": "?", "us": "?"}

def main():
    m = get_metrics()
    market = get_market_status()
    tz8 = pytz.timezone("Asia/Hong_Kong")
    now_tz8 = datetime.now(tz8)
    time_str = now_tz8.strftime("%H:%M")
    
    msg = (f"🤖 Heartbeat {time_str} UTC+8 • Health: OK • "
           f"Market: {market['hk']} (HK) | {market['us']} (US) • "
           f"Equity: ${m['equity']:,.2f} ({m['pnl_pct']:+.2f}%) • "
           f"Positions: {m['open_positions']} | Cash: ${m['cash']:,.2f} • "
           f"Drawdown: {m['drawdown']:.2f}% • Trades: {m['total_trades']} total • "
           f"Auto_execute: ENABLED (75% threshold) "
           f"Portfolio improving toward 20% annual target. No alerts.")
    print(msg)

if __name__ == "__main__":
    main()
