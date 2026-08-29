"""Compact operational status report for trading_system_v3.

Run after a scan cycle (or standalone) to summarize portfolio state,
recent trades, open risk events, and recent lessons -- everything a
supervisor (human or agent) needs to decide "is anything wrong here"
without opening three separate SQLite files by hand.

Usage:
    .venv/bin/python -m scripts.status_report --config config.yaml
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from trading_system_v3.config.loader import load_config


def _rows(db_path: str, query: str, params: tuple = ()) -> list[tuple]:
    if not Path(db_path).exists():
        return []
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(query, params).fetchall()
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Print a compact status report")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--recent-trades", type=int, default=10)
    parser.add_argument("--recent-lessons", type=int, default=5)
    args = parser.parse_args()

    cfg = load_config(args.config)

    print("=== Portfolio ===")
    state_rows = _rows(cfg.db_path, "SELECT key, value FROM state")
    state = dict(state_rows)
    if state:
        print(f"cash: {float(state.get('cash', 0)):.2f}")
        print(f"day_start_equity: {float(state.get('day_start_equity', 0)):.2f}")
        print(f"day_realized_pnl: {float(state.get('day_realized_pnl', 0)):.2f}")
    else:
        print("(no portfolio.sqlite yet -- no cycle has run)")

    positions = _rows(cfg.db_path, "SELECT symbol, quantity, avg_price, stop_loss_price FROM positions")
    print(f"open positions: {len(positions)}")
    for symbol, qty, avg_price, stop in positions:
        print(f"  {symbol}: qty={qty} avg_price={avg_price:.2f} stop={stop}")

    print(f"\n=== Last {args.recent_trades} trades ===")
    trades = _rows(
        cfg.db_path,
        "SELECT timestamp, symbol, action, quantity, filled_price, realized_pnl FROM trades "
        "ORDER BY id DESC LIMIT ?",
        (args.recent_trades,),
    )
    if not trades:
        print("(none)")
    for ts, symbol, action, qty, price, pnl in trades:
        print(f"  {ts} {action} {symbol} qty={qty} @ {price:.2f} realized_pnl={pnl:.2f}")

    print("\n=== Open risk events (cooldowns / circuit breaker) ===")
    events = _rows(
        cfg.risk_memory_db_path,
        "SELECT timestamp, symbol, event_type, details, expires_at FROM risk_events ORDER BY id DESC LIMIT 20",
    )
    if not events:
        print("(none)")
    for ts, symbol, event_type, details, expires_at in events:
        print(f"  {ts} {symbol} {event_type}: {details} (expires {expires_at})")

    print(f"\n=== Last {args.recent_lessons} lessons (StrategyActor semantic memory) ===")
    lessons = _rows(
        cfg.strategy_memory_db_path,
        "SELECT created_at, text FROM lessons ORDER BY id DESC LIMIT ?",
        (args.recent_lessons,),
    )
    if not lessons:
        print("(none)")
    for created_at, text in lessons:
        print(f"  {created_at}: {text}")

    print("\n=== Pending (unresolved) decisions ===")
    pending = _rows(
        cfg.strategy_memory_db_path,
        "SELECT symbol, timestamp, action, confidence FROM decisions WHERE executed = 1 AND outcome_pnl IS NULL "
        "ORDER BY id DESC LIMIT 20",
    )
    print(f"open (executed, unresolved) decisions: {len(pending)}")
    for symbol, ts, action, conf in pending:
        print(f"  {symbol} {action} conf={conf:.2f} at {ts}")


if __name__ == "__main__":
    main()
