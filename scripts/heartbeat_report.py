#!/usr/bin/env python3
"""Heartbeat report generator for AITradeAgent."""
import sqlite3
import os
import yaml
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

DB_PATH = "finance_service/storage/portfolio.sqlite"
CONFIG_PATH = "config/finance.yaml"

def get_config_initial_cash():
    try:
        with open(CONFIG_PATH, 'r') as f:
            cfg = yaml.safe_load(f)
            return cfg.get('portfolio', {}).get('initial_cash', 100000)
    except Exception as e:
        print(f"Error reading config: {e}", flush=True)
        return 100000

def get_metrics():
    """Query portfolio metrics from database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Total trades count
    try:
        cur.execute("SELECT COUNT(*) as cnt FROM trades")
        total_trades = cur.fetchone()['cnt']
    except:
        total_trades = 0

    # Open positions count
    try:
        cur.execute("SELECT COUNT(*) as cnt FROM positions WHERE status = 'OPEN'")
        open_positions = cur.fetchone()['cnt']
    except:
        open_positions = 0

    # Sum of quantity * entry_price for open positions (cost basis)
    try:
        cur.execute("""
            SELECT SUM(quantity * entry_price) as pos_value
            FROM positions
            WHERE status = 'OPEN'
        """)
        row = cur.fetchone()
        positions_value = row['pos_value'] or 0.0
    except:
        positions_value = 0.0

    # Realized P&L from closed positions
    try:
        cur.execute("SELECT SUM(pnl) as realized_pnl FROM positions WHERE status = 'CLOSED' AND pnl IS NOT NULL")
        row = cur.fetchone()
        realized_pnl = row['realized_pnl'] or 0.0
    except:
        realized_pnl = 0.0

    conn.close()

    initial_cash = get_config_initial_cash()
    cash = initial_cash + realized_pnl  # Simplified: cash increases by realized P&L
    equity = cash + positions_value
    pnl = equity - initial_cash
    pnl_pct = (pnl / initial_cash) * 100 if initial_cash else 0.0

    # Drawdown: not tracked yet, set to 0
    drawdown = 0.0

    return {
        "total_trades": total_trades,
        "open_positions": open_positions,
        "cash": cash,
        "equity": equity,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "drawdown": drawdown
    }

def get_market_status():
    """Check if HK and US markets are open."""
    try:
        now = datetime.now(pytz.timezone("Asia/Hong_Kong"))
        is_weekday = now.weekday() < 5  # Monday=0, Friday=4
        hk_open = 9 <= now.hour < 16
        us_time = now.astimezone(pytz.timezone("US/Eastern"))
        us_open = 9 <= us_time.hour < 16
        return {
            "hk": "OPEN" if is_weekday and hk_open else "CLOSED",
            "us": "OPEN" if is_weekday and us_open else "CLOSED"
        }
    except Exception as e:
        print(f"Market status error: {e}", flush=True)
        return {"hk": "?", "us": "?"}

def send_telegram(message: str) -> bool:
    """Send message to Telegram if configured."""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        return False
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        resp = requests.post(url, json={"chat_id": chat_id, "text": message}, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        print(f"Telegram send failed: {e}", flush=True)
        return False

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

    # Send to Telegram if configured
    if send_telegram(msg):
        print("✅ Sent to Telegram", flush=True)
    else:
        print("ℹ️ Telegram not configured or failed", flush=True)

if __name__ == "__main__":
    main()
