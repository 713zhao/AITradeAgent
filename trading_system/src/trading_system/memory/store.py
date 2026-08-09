"""MemoryStore: persistent episodic + semantic memory shared by the
reasoning agents (StrategyAgent, RiskAgent, LearningAgent).

Design: only the agents that make judgment calls get memory. Mechanical
agents (Data/Analysis/Execution/Portfolio) stay stateless; their state is
already the DataAgent cache and the PortfolioStore ledger.

Three tables:
  - decisions: every trade proposal ever made (not just executed ones),
    with outcome_pnl backfilled once the resulting position closes. This
    is StrategyAgent's episodic memory.
  - lessons: short distilled text written by LearningAgent after
    reviewing closed trades. This is StrategyAgent's semantic memory,
    injected into its system prompt.
  - risk_events: cooldowns and circuit-breaker triggers, persisted so
    RiskAgent's state survives a restart (previously an in-memory dict).
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    action TEXT NOT NULL,
    confidence REAL NOT NULL,
    target_weight REAL,
    reasoning TEXT,
    proposed_by TEXT,
    executed INTEGER NOT NULL DEFAULT 0,
    outcome_pnl REAL,
    outcome_recorded_at TEXT
);
CREATE TABLE IF NOT EXISTS lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    scope TEXT NOT NULL,
    text TEXT NOT NULL,
    source_decision_ids TEXT
);
CREATE TABLE IF NOT EXISTS risk_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    symbol TEXT NOT NULL,
    event_type TEXT NOT NULL,
    details TEXT,
    expires_at TEXT
);
"""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class DecisionMemory:
    id: int
    symbol: str
    timestamp: str
    action: str
    confidence: float
    reasoning: str
    proposed_by: str
    outcome_pnl: float | None


class MemoryStore:
    def __init__(self, db_path: str) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    # --- decisions / episodic memory -------------------------------------

    def log_decision(
        self, symbol: str, action: str, confidence: float, target_weight: float | None,
        reasoning: str, proposed_by: str, executed: bool = False,
    ) -> int:
        cur = self._conn.execute(
            "INSERT INTO decisions(symbol, timestamp, action, confidence, target_weight, reasoning, "
            "proposed_by, executed) VALUES (?,?,?,?,?,?,?,?)",
            (symbol, _utcnow().isoformat(), action, confidence, target_weight, reasoning,
             proposed_by, int(executed)),
        )
        self._conn.commit()
        return cur.lastrowid

    def mark_executed(self, decision_id: int) -> None:
        self._conn.execute("UPDATE decisions SET executed = 1 WHERE id = ?", (decision_id,))
        self._conn.commit()

    def backfill_outcome_for_symbol(self, symbol: str, realized_pnl: float) -> None:
        """Attaches a realized P&L to the most recent executed BUY decision
        for this symbol that hasn't been resolved yet (mirrors the
        RiskAgent policy of at most one open position per symbol)."""
        row = self._conn.execute(
            "SELECT id FROM decisions WHERE symbol = ? AND action = 'BUY' AND executed = 1 "
            "AND outcome_pnl IS NULL ORDER BY id DESC LIMIT 1",
            (symbol,),
        ).fetchone()
        if row is None:
            return
        self._conn.execute(
            "UPDATE decisions SET outcome_pnl = ?, outcome_recorded_at = ? WHERE id = ?",
            (realized_pnl, _utcnow().isoformat(), row[0]),
        )
        self._conn.commit()

    def recent_decisions(self, symbol: str, limit: int = 5) -> list[DecisionMemory]:
        rows = self._conn.execute(
            "SELECT id, symbol, timestamp, action, confidence, reasoning, proposed_by, outcome_pnl "
            "FROM decisions WHERE symbol = ? ORDER BY id DESC LIMIT ?",
            (symbol, limit),
        ).fetchall()
        return [DecisionMemory(*r) for r in rows]

    def win_rate_summary(self, symbol: str) -> str:
        rows = self._conn.execute(
            "SELECT outcome_pnl FROM decisions WHERE symbol = ? AND outcome_pnl IS NOT NULL",
            (symbol,),
        ).fetchall()
        outcomes = [r[0] for r in rows]
        if not outcomes:
            return f"No resolved trade history yet for {symbol}."
        wins = sum(1 for o in outcomes if o > 0)
        avg = sum(outcomes) / len(outcomes)
        return f"{symbol} track record: {wins}/{len(outcomes)} profitable, avg P&L {avg:.2f} over {len(outcomes)} closed trades."

    def unresolved_decisions_since(self, since_id: int = 0, limit: int = 100) -> list[DecisionMemory]:
        rows = self._conn.execute(
            "SELECT id, symbol, timestamp, action, confidence, reasoning, proposed_by, outcome_pnl "
            "FROM decisions WHERE id > ? AND outcome_pnl IS NOT NULL ORDER BY id ASC LIMIT ?",
            (since_id, limit),
        ).fetchall()
        return [DecisionMemory(*r) for r in rows]

    # --- lessons / semantic memory ----------------------------------------

    def add_lesson(self, text: str, scope: str = "global", source_decision_ids: list[int] | None = None) -> int:
        cur = self._conn.execute(
            "INSERT INTO lessons(created_at, scope, text, source_decision_ids) VALUES (?,?,?,?)",
            (_utcnow().isoformat(), scope, text, ",".join(str(i) for i in (source_decision_ids or []))),
        )
        self._conn.commit()
        return cur.lastrowid

    def recent_lessons(self, scope: str = "global", limit: int = 5) -> list[str]:
        rows = self._conn.execute(
            "SELECT text FROM lessons WHERE scope = ? ORDER BY id DESC LIMIT ?",
            (scope, limit),
        ).fetchall()
        return [r[0] for r in rows]

    # --- risk events / cooldowns -------------------------------------------

    def set_cooldown(self, symbol: str, until: datetime, reason: str = "post_loss_cooldown") -> None:
        self._conn.execute(
            "INSERT INTO risk_events(timestamp, symbol, event_type, details, expires_at) VALUES (?,?,?,?,?)",
            (_utcnow().isoformat(), symbol, "cooldown", reason, until.isoformat()),
        )
        self._conn.commit()

    def cooldown_until(self, symbol: str) -> datetime | None:
        row = self._conn.execute(
            "SELECT expires_at FROM risk_events WHERE symbol = ? AND event_type = 'cooldown' "
            "ORDER BY id DESC LIMIT 1",
            (symbol,),
        ).fetchone()
        if row is None or row[0] is None:
            return None
        return datetime.fromisoformat(row[0])

    def record_risk_event(self, symbol: str, event_type: str, details: str) -> None:
        self._conn.execute(
            "INSERT INTO risk_events(timestamp, symbol, event_type, details) VALUES (?,?,?,?)",
            (_utcnow().isoformat(), symbol, event_type, details),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
