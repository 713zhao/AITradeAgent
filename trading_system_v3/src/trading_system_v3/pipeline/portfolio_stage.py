"""PortfolioStore + PortfolioStage: the single writer of cash, positions,
and trade history, backed by SQLite. Mechanical/stateless from the
pipeline's perspective in the sense that it holds no judgment/opinion --
it just durably records what the isolated actors decided and the broker
filled -- so it is not one of the isolated actors either, but it *is*
still the single source of truth RiskActor is told about via
``RiskRequest.equity`` / ``open_position_count`` on every cycle.
"""
from __future__ import annotations

import asyncio
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

from trading_system_v3.core.models import Action, ExecutionResult, Position

SCHEMA = """
CREATE TABLE IF NOT EXISTS state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS positions (
    symbol TEXT PRIMARY KEY,
    quantity REAL NOT NULL,
    avg_price REAL NOT NULL,
    stop_loss_price REAL
);
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    action TEXT NOT NULL,
    quantity REAL NOT NULL,
    filled_price REAL NOT NULL,
    commission REAL NOT NULL,
    realized_pnl REAL NOT NULL DEFAULT 0,
    order_id TEXT NOT NULL,
    timestamp TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS equity_history (
    timestamp TEXT NOT NULL,
    equity REAL NOT NULL
);
"""


class PortfolioStore:
    def __init__(self, db_path: str, starting_cash: float = 100_000.0) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.executescript(SCHEMA)
        self._conn.commit()
        if self._get_state("cash") is None:
            self._set_state("cash", str(starting_cash))
        if self._get_state("day") is None:
            self._set_state("day", date.today().isoformat())
            self._set_state("day_start_equity", str(starting_cash))
            self._set_state("day_realized_pnl", "0.0")

    def _get_state(self, key: str) -> str | None:
        row = self._conn.execute("SELECT value FROM state WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def _set_state(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO state(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        self._conn.commit()

    @property
    def cash(self) -> float:
        return float(self._get_state("cash") or 0.0)

    def positions(self) -> dict[str, Position]:
        rows = self._conn.execute("SELECT symbol, quantity, avg_price, stop_loss_price FROM positions").fetchall()
        return {
            r[0]: Position(symbol=r[0], quantity=r[1], avg_price=r[2], stop_loss_price=r[3])
            for r in rows if r[1] > 0
        }

    def _roll_day_if_needed(self, equity_now: float) -> None:
        today = date.today().isoformat()
        if self._get_state("day") != today:
            self._set_state("day", today)
            self._set_state("day_start_equity", str(equity_now))
            self._set_state("day_realized_pnl", "0.0")

    def day_start_equity(self) -> float:
        return float(self._get_state("day_start_equity") or 0.0)

    def day_realized_pnl(self) -> float:
        return float(self._get_state("day_realized_pnl") or 0.0)

    def apply_execution(self, execution: ExecutionResult, stop_loss_price: float | None) -> float:
        cash = self.cash
        pos = self.positions().get(execution.symbol)
        realized = 0.0

        if execution.action == Action.BUY:
            cost = execution.quantity * execution.filled_price + execution.commission
            cash -= cost
            if pos is None:
                new_qty, new_avg = execution.quantity, execution.filled_price
            else:
                total_qty = pos.quantity + execution.quantity
                new_avg = (pos.quantity * pos.avg_price + execution.quantity * execution.filled_price) / total_qty
                new_qty = total_qty
            self._conn.execute(
                "INSERT INTO positions(symbol, quantity, avg_price, stop_loss_price) VALUES(?,?,?,?) "
                "ON CONFLICT(symbol) DO UPDATE SET quantity=excluded.quantity, avg_price=excluded.avg_price, "
                "stop_loss_price=excluded.stop_loss_price",
                (execution.symbol, new_qty, new_avg, stop_loss_price),
            )
        else:  # SELL
            proceeds = execution.quantity * execution.filled_price - execution.commission
            cash += proceeds
            if pos is not None:
                realized = (execution.filled_price - pos.avg_price) * execution.quantity - execution.commission
                remaining = pos.quantity - execution.quantity
                if remaining <= 1e-9:
                    self._conn.execute("DELETE FROM positions WHERE symbol = ?", (execution.symbol,))
                else:
                    self._conn.execute(
                        "UPDATE positions SET quantity = ? WHERE symbol = ?", (remaining, execution.symbol)
                    )

        self._set_state("cash", str(cash))
        self._conn.execute(
            "INSERT INTO trades(symbol, action, quantity, filled_price, commission, realized_pnl, order_id, timestamp) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (
                execution.symbol, execution.action.value, execution.quantity, execution.filled_price,
                execution.commission, realized, execution.order_id, execution.timestamp.isoformat(),
            ),
        )
        if realized != 0.0:
            self._set_state("day_realized_pnl", str(self.day_realized_pnl() + realized))
        self._conn.commit()
        return realized

    def record_equity(self, prices: dict[str, float]) -> float:
        total = self.cash
        for sym, pos in self.positions().items():
            total += pos.quantity * prices.get(sym, pos.avg_price)
        self._roll_day_if_needed(total)
        self._conn.execute(
            "INSERT INTO equity_history(timestamp, equity) VALUES(?, ?)",
            (datetime.now(timezone.utc).isoformat(), total),
        )
        self._conn.commit()
        return total

    def trade_history(self, limit: int = 200) -> list[dict]:
        rows = self._conn.execute(
            "SELECT symbol, action, quantity, filled_price, commission, realized_pnl, order_id, timestamp "
            "FROM trades ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        cols = ["symbol", "action", "quantity", "filled_price", "commission", "realized_pnl", "order_id", "timestamp"]
        return [dict(zip(cols, r)) for r in rows]

    def close(self) -> None:
        self._conn.close()


class PortfolioStage:
    def __init__(self, store: PortfolioStore) -> None:
        self.store = store

    async def apply(self, execution: ExecutionResult, stop_loss_price: float | None = None) -> float:
        return await asyncio.to_thread(self.store.apply_execution, execution, stop_loss_price)
