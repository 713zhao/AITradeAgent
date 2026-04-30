#!/usr/bin/env python3
"""Heartbeat report generator for AITradeAgent — rich hourly portfolio format."""
import os
import json
import sqlite3
import requests
import concurrent.futures
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

API_BASE      = os.getenv("FINANCE_API_URL", "http://127.0.0.1:8801")
WORKSPACE     = Path(__file__).parent.parent
BACKTEST_DB   = WORKSPACE / "finance_service" / "storage" / "backtest.sqlite"
NAMES_CACHE   = WORKSPACE / "memory" / "symbol_names.json"
STALE_MINUTES = 20

# Assessment thresholds
TARGET_CAGR_PCT    = 20.0
TARGET_SHARPE      = 1.0
DRAWDOWN_LIMIT_PCT = -20.0


# ── Data fetchers ────────────────────────────────────────────────────────────

def get_portfolio_state():
    try:
        resp = requests.get(f"{API_BASE}/portfolio/state", timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[heartbeat] API fetch failed: {e}", flush=True)
        return None


def get_market_status():
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


def get_symbol_names(symbols: list) -> dict:
    """Return {symbol: short_name} using a local JSON cache; fetch missing ones via yfinance."""
    cache = {}
    if NAMES_CACHE.exists():
        try:
            cache = json.loads(NAMES_CACHE.read_text())
        except Exception:
            cache = {}

    missing = [s for s in symbols if s not in cache]
    if missing:
        try:
            import yfinance as yf

            def _fetch(sym):
                try:
                    info = yf.Ticker(sym).info or {}
                    return sym, (info.get("shortName") or info.get("longName") or sym)
                except Exception:
                    return sym, sym

            with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
                for sym, name in ex.map(_fetch, missing):
                    cache[sym] = name

            NAMES_CACHE.parent.mkdir(parents=True, exist_ok=True)
            NAMES_CACHE.write_text(json.dumps(cache, indent=2))
        except Exception as e:
            print(f"[heartbeat] Name fetch failed: {e}", flush=True)
            for sym in missing:
                cache[sym] = sym

    return cache


def get_backtest_result(strategy_name: str = None):
    if not BACKTEST_DB.exists():
        return None
    try:
        conn = sqlite3.connect(str(BACKTEST_DB))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        if strategy_name:
            cur.execute(
                "SELECT * FROM backtest_runs WHERE run_name LIKE ? "
                "ORDER BY created_at DESC LIMIT 1",
                (f"%{strategy_name}%",),
            )
        else:
            cur.execute("SELECT * FROM backtest_runs ORDER BY created_at DESC LIMIT 1")
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception as e:
        print(f"[heartbeat] Backtest DB read failed: {e}", flush=True)
        return None


def get_active_strategy():
    cfg = WORKSPACE / "config" / "finance.yaml"
    if not cfg.exists():
        return "sma50_trend_regime"
    for line in cfg.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("type:") and "sma" in stripped.lower():
            return stripped.split(":", 1)[1].strip()
    return "sma50_trend_regime"


# ── Report builders ──────────────────────────────────────────────────────────

def _fmt_pnl(upnl: float) -> str:
    """Format a P&L dollar value, avoiding the '-0' display artifact."""
    rounded = round(upnl, 2)
    if rounded == 0.0:
        return f"{'0':>9}"
    sign = "+" if rounded > 0 else ""
    return f"{sign}{rounded:>8.2f}"


def build_assessment_lines(bt: dict) -> list:
    cagr   = bt.get("cagr_pct", 0.0)
    sharpe = bt.get("sharpe_ratio", 0.0)
    dd     = bt.get("max_drawdown_pct", 0.0)
    lines  = []

    cagr_ok = cagr >= TARGET_CAGR_PCT
    lines.append(
        f"{'✅' if cagr_ok else '⚠️'} CAGR {'on target' if cagr_ok else 'below target'}: "
        f"{cagr:.1f}% {'≥' if cagr_ok else '<'} {TARGET_CAGR_PCT:.1f}%"
    )
    sharpe_ok = sharpe >= TARGET_SHARPE
    lines.append(
        f"{'✅' if sharpe_ok else '⚠️'} Sharpe {'sufficient' if sharpe_ok else 'low'}: "
        f"{sharpe:.2f} {'≥' if sharpe_ok else '<'} {TARGET_SHARPE:.1f}"
    )
    dd_ok = dd >= DRAWDOWN_LIMIT_PCT
    lines.append(
        f"{'✅' if dd_ok else '⚠️'} Drawdown {'within limit' if dd_ok else 'excessive'}: "
        f"{dd:.1f}%"
    )
    return lines


def build_recommendations(bt: dict) -> list:
    cagr   = bt.get("cagr_pct", 0.0)
    sharpe = bt.get("sharpe_ratio", 0.0)
    dd     = bt.get("max_drawdown_pct", 0.0)
    recs   = []

    if cagr < TARGET_CAGR_PCT and sharpe < TARGET_SHARPE:
        recs.append("Improve risk-adjusted returns: add trend filter or increase take-profit ratios")
    elif cagr < TARGET_CAGR_PCT:
        recs.append("Increase CAGR: widen take-profit targets or expand universe to more volatile symbols")
    if sharpe < TARGET_SHARPE:
        recs.append("Reduce volatility drag: tighten position sizing or add regime filter to avoid sideways markets")
    if dd < DRAWDOWN_LIMIT_PCT:
        recs.append("Tighten stop-losses or reduce max concurrent positions to limit drawdown")
    if not recs:
        recs.append("Strategy performing within targets — continue monitoring")
    return recs


def send_telegram(message: str) -> bool:
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id   = os.getenv("TELEGRAM_CHAT_ID")
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
    m            = data.get("equity_metrics", {})
    _raw_pos     = data.get("positions", [])
    last_updated = data.get("last_updated")

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
    pnl_sign       = "+" if total_pnl > 0 else ""
    upnl_sign      = "+" if unrealized_pnl > 0 else ""

    open_markets = []
    if market["us"]:
        open_markets.append("🇺🇸 US")
    if market["hk"]:
        open_markets.append("🇭🇰 HK")
    market_str = (" & ".join(open_markets) + " market open") if open_markets else "markets closed"

    now_utc = datetime.now(timezone.utc).strftime("%H:%M UTC")

    if last_updated:
        try:
            updated_dt = datetime.fromisoformat(last_updated.replace("Z", "+00:00"))
            if updated_dt.tzinfo is None:
                updated_dt = updated_dt.replace(tzinfo=timezone.utc)
            age_mins = (datetime.now(timezone.utc) - updated_dt).total_seconds() / 60
            data_line = (
                f"✅ Prices: live (updated <{STALE_MINUTES}m ago)"
                if age_mins <= STALE_MINUTES
                else f"⚠️ Prices: stale ({age_mins:.0f}m old)"
            )
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
        # Fetch symbol names (from cache, no blocking requests on subsequent runs)
        names = get_symbol_names(list(positions.keys()))

        lines.append("*Positions:*")
        lines.append("```")
        # Column layout: Sym(8) Name(12) Qty(5) Avg(7) Cur(7) P&L(9) %(6)
        lines.append(f"{'Sym':<8} {'Name':<12} {'Qty':>5} {'Avg':>7} {'Cur':>7} {'P&L':>9} {'%':>6}")
        lines.append("-" * 60)
        for sym, pos in sorted(positions.items()):
            qty      = pos.get("quantity", 0)
            avg      = pos.get("avg_cost", 0)
            cur      = pos.get("current_price", avg)
            upnl     = pos.get("unrealized_pnl", (cur - avg) * qty)
            upnl_pct = ((cur - avg) / avg * 100) if avg else 0
            name     = (names.get(sym) or sym)[:12]
            pnl_str  = _fmt_pnl(upnl)
            lines.append(
                f"{sym:<8} {name:<12} {qty:>5} {avg:>7.2f} {cur:>7.2f} {pnl_str} {upnl_pct:>+5.1f}%"
            )
        lines.append("```\n")

    # ── Strategy + Backtest Assessment ──────────────────────────────────────
    strategy = get_active_strategy()
    bt = get_backtest_result(strategy)
    if bt:
        start = bt.get("start_date", "")[:10]
        end   = bt.get("end_date", "")[:10]
        lines.append(f"*📈 Strategy:* `{bt.get('run_name', strategy)}`")
        lines.append(f"Period: {start} to {end}\n")

        lines.append("*🔍 Assessment:*")
        for a in build_assessment_lines(bt):
            lines.append(f"  {a}")
        lines.append("")

        lines.append("*🔧 Recommended Actions:*")
        for r in build_recommendations(bt):
            lines.append(f"  • {r}")

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
