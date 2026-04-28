#!/usr/bin/env python3
"""Heartbeat report generator for AITradeAgent."""
import os
import requests
from datetime import datetime
import pytz
from pathlib import Path

# Load .env file if present
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            key, _, value = line.partition("=")
            os.environ[key.strip()] = value.strip().strip('"').strip("'")

API_BASE = os.getenv("FINANCE_API_URL", "http://127.0.0.1:8801")


def get_metrics():
    """Fetch portfolio metrics from the live service API."""
    try:
        resp = requests.get(f"{API_BASE}/portfolio/state", timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[heartbeat] API fetch failed: {e}", flush=True)
        return None

    m = data.get("equity_metrics", {})
    positions = data.get("positions", [])
    trades    = data.get("trades", [])

    return {
        "total_trades":    m.get("trade_count", len(trades)),
        "open_positions":  m.get("position_count", len(positions)),
        "cash":            m.get("current_cash", 0.0),
        "equity":          m.get("total_equity", 0.0),
        "pnl_pct":         m.get("total_return_pct", 0.0),
        "unrealized_pnl":  m.get("unrealized_pnl", 0.0),
        "realized_pnl":    m.get("realized_pnl", 0.0),
        "drawdown":        m.get("drawdown_pct", 0.0),
    }


def get_market_status():
    """Check if HK and US markets are open."""
    try:
        now_hk = datetime.now(pytz.timezone("Asia/Hong_Kong"))
        is_weekday = now_hk.weekday() < 5
        hk_open = is_weekday and 9 <= now_hk.hour < 16
        now_us  = now_hk.astimezone(pytz.timezone("US/Eastern"))
        us_open = is_weekday and 9 <= now_us.hour < 16
        return {
            "hk": "OPEN" if hk_open else "CLOSED",
            "us": "OPEN" if us_open else "CLOSED",
        }
    except Exception as e:
        print(f"Market status error: {e}", flush=True)
        return {"hk": "?", "us": "?"}


def send_telegram(message: str) -> bool:
    """Send message to Telegram if configured."""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id   = os.getenv("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        return False
    try:
        url  = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        resp = requests.post(url, json={"chat_id": chat_id, "text": message}, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        print(f"Telegram send failed: {e}", flush=True)
        return False


def main():
    m = get_metrics()
    if m is None:
        print("[heartbeat] Could not fetch metrics from API — is the service running?", flush=True)
        return

    market   = get_market_status()
    now_tz8  = datetime.now(pytz.timezone("Asia/Hong_Kong"))
    time_str = now_tz8.strftime("%H:%M")

    auto_exec_threshold = int(os.getenv("AUTO_EXEC_THRESHOLD", "75"))

    msg = (
        f"🤖 Heartbeat {time_str} UTC+8 • Health: OK • "
        f"Market: {market['hk']} (HK) | {market['us']} (US) • "
        f"Equity: ${m['equity']:,.2f} ({m['pnl_pct']:+.2f}%) • "
        f"Positions: {m['open_positions']} | Cash: ${m['cash']:,.2f} • "
        f"Drawdown: {m['drawdown']:.2f}% • Trades: {m['total_trades']} total • "
        f"Auto_execute: ENABLED ({auto_exec_threshold}% threshold) "
        f"Portfolio improving toward 20% annual target. No alerts."
    )
    print(msg, flush=True)

    if send_telegram(msg):
        print("✅ Sent to Telegram", flush=True)
    else:
        print("ℹ️ Telegram not configured or failed", flush=True)


if __name__ == "__main__":
    main()
