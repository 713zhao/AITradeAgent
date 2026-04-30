#!/usr/bin/env python3
"""Heartbeat report generator for AITradeAgent — rich hourly portfolio format."""
import os
import requests
from datetime import datetime, timezone
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
STALE_MINUTES = 20


def get_portfolio_state():
    """Fetch full portfolio state from the live service API."""
    try:
        resp = requests.get(f"{API_BASE}/portfolio/state", timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[heartbeat] API fetch failed: {e}", flush=True)
        return None


def get_market_status():
    """Check if HK and US markets are currently open."""
    try:
        now_hk = datetime.now(pytz.timezone("Asia/Hong_Kong"))
        is_weekday = now_hk.weekday() < 5
        hk_open = is_weekday and 9 <= now_hk.hour < 16
        now_us = now_hk.astimezone(pytz.timezone("US/Eastern"))
        us_open = is_weekday and 9 <= now_us.hour < 16
        return {"hk": hk_open, "us": us_open}
    except Exception as e:
        print(f"Market status error: {e}", flush=True)
        return {"hk": False, "us": False}


def send_telegram(message: str) -> bool:
    """Send message to Telegram if configured."""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        return False
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        resp = requests.post(
            url,
            json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"},
            timeout=10,
        )
        return resp.status_code == 200
    except Exception as e:
        print(f"Telegram send failed: {e}", flush=True)
        return False


def build_report(data: dict, market: dict) -> str:
    """Build the rich hourly portfolio report string (ported from health_agent.py)."""
    m = data.get("equity_metrics", {})
    _raw_pos = data.get("positions", [])
    last_updated = data.get("last_updated")

    # Normalise positions to dict keyed by symbol
    if isinstance(_raw_pos, list):
        positions = {p["symbol"]: p for p in _raw_pos if "symbol" in p}
    else:
        positions = _raw_pos

    equity         = m.get("total_equity", 0.0)
    cash           = m.get("current_cash", 0.0)
    gross          = m.get("gross_position_value", 0.0)
    ret            = m.get("total_return_pct", 0.0)
    dd             = m.get("drawdown_pct", 0.0)
    n_pos          = len(positions)
    unrealized_pnl = m.get("unrealized_pnl", 0.0)
    realized_pnl   = m.get("realized_pnl", 0.0)
    total_pnl      = m.get("total_pnl", unrealized_pnl + realized_pnl)
    pnl_sign       = "+" if total_pnl >= 0 else ""
    upnl_sign      = "+" if unrealized_pnl >= 0 else ""

    # Market label
    open_markets = []
    if market["us"]:
        open_markets.append("🇺🇸 US")
    if market["hk"]:
        open_markets.append("🇭🇰 HK")
    market_str = (" & ".join(open_markets) + " market open") if open_markets else "markets closed"

    now_utc = datetime.now(timezone.utc).strftime("%H:%M UTC")

    # Data freshness indicator
    if last_updated:
        try:
            updated_dt = datetime.fromisoformat(last_updated.replace("Z", "+00:00"))
            if updated_dt.tzinfo is None:
                updated_dt = updated_dt.replace(tzinfo=timezone.utc)
            age_mins = (datetime.now(timezone.utc) - updated_dt).total_seconds() / 60
            if age_mins <= STALE_MINUTES:
                data_line = f"✅ Prices: live (updated <{STALE_MINUTES}m ago)"
            else:
                data_line = f"⚠️ Prices: stale ({age_mins:.0f}m old)"
        except Exception:
            data_line = "ℹ️ Prices: cached"
    else:
        data_line = "ℹ️ Prices: cached"

    lines = [f"⏰ *Hourly Portfolio — {now_utc}* ({market_str})\n"]
    lines.append(f"💼 Equity: *${equity:,.2f}*  |  Return: {ret:+.2f}%  |  Drawdown: {dd:.2f}%")
    lines.append(f"💵 Cash: ${cash:,.2f}   📈 Positions: ${gross:,.2f}  ({n_pos} open)")
    lines.append(f"📊 P&L: *{pnl_sign}${total_pnl:,.2f}*  (Unrealized: {upnl_sign}${unrealized_pnl:,.2f}  |  Realized: ${realized_pnl:,.2f})")
    lines.append(f"{data_line}\n")

    if positions:
        lines.append("*Positions:*")
        lines.append("```")
        lines.append(f"{'Sym':<8} {'Qty':>5} {'Avg':>7} {'Cur':>7} {'P&L':>9} {'%':>6}")
        lines.append("-" * 47)
        for sym, pos in sorted(positions.items()):
            qty      = pos.get("quantity", 0)
            avg      = pos.get("avg_cost", 0)
            cur      = pos.get("current_price", avg)
            upnl     = pos.get("unrealized_pnl", (cur - avg) * qty)
            upnl_pct = ((cur - avg) / avg * 100) if avg else 0
            sign     = "+" if upnl > 0 else ""
            lines.append(
                f"{sym:<8} {qty:>5} {avg:>7.2f} {cur:>7.2f} {sign}{upnl:>8,.0f} {upnl_pct:>+5.1f}%"
            )
        lines.append("```")

    return "\n".join(lines)


def main():
    data = get_portfolio_state()
    if data is None:
        print("[heartbeat] Could not fetch metrics from API — is the service running?", flush=True)
        return

    market = get_market_status()
    msg = build_report(data, market)
    print(msg, flush=True)

    if send_telegram(msg):
        print("✅ Sent to Telegram", flush=True)
    else:
        print("ℹ️ Telegram not configured or failed", flush=True)


if __name__ == "__main__":
    main()
