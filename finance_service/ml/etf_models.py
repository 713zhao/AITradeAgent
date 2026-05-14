"""ETF data models and SQLite database functions for Layer 4 ETF Intelligence."""
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

RECOMMENDATION_TYPES = ("sector_rotation", "hedge", "correlation")


@dataclass
class ETFSnapshot:
    etf_symbol: str
    date: str
    price: float = 0.0
    volume: int = 0
    ytd_return: float = 0.0
    momentum_20d: float = 0.0
    volatility_20d: float = 0.0
    dividend_yield: float = 0.0
    aum: float = 0.0
    sector: str = "Unknown"
    asset_class: str = "Equity"
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_db_tuple(self):
        return (
            self.etf_symbol, self.date,
            round(self.price, 4), int(self.volume),
            round(self.ytd_return, 6), round(self.momentum_20d, 6),
            round(self.volatility_20d, 6), round(self.dividend_yield, 6),
            round(self.aum, 2), self.sector, self.asset_class,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "etf_symbol": self.etf_symbol, "date": self.date,
            "price": self.price, "volume": self.volume,
            "ytd_return": self.ytd_return, "momentum_20d": self.momentum_20d,
            "volatility_20d": self.volatility_20d, "dividend_yield": self.dividend_yield,
            "aum": self.aum, "sector": self.sector, "asset_class": self.asset_class,
            "created_at": self.created_at,
        }


@dataclass
class ETFRecommendation:
    recommendation_date: str
    etf_symbol: str
    recommendation_type: str
    confidence: float = 0.0
    reason: str = ""
    sector: str = "Unknown"
    correlation_to_portfolio: float = 0.0
    suggested_allocation_pct: float = 0.0
    win_probability_estimate: float = 0.0
    llm_response: Any = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def __post_init__(self):
        assert self.recommendation_type in RECOMMENDATION_TYPES, (
            f"recommendation_type must be one of {RECOMMENDATION_TYPES}, got {self.recommendation_type!r}"
        )

    def to_db_tuple(self):
        return (
            self.recommendation_date, self.etf_symbol, self.recommendation_type,
            round(self.confidence, 4), self.reason, self.sector,
            round(self.correlation_to_portfolio, 4),
            round(self.suggested_allocation_pct, 2),
            round(self.win_probability_estimate, 4),
            json.dumps(self.llm_response) if not isinstance(self.llm_response, str) else self.llm_response,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recommendation_date": self.recommendation_date,
            "etf_symbol": self.etf_symbol,
            "recommendation_type": self.recommendation_type,
            "confidence": self.confidence, "reason": self.reason,
            "sector": self.sector,
            "correlation_to_portfolio": self.correlation_to_portfolio,
            "suggested_allocation_pct": self.suggested_allocation_pct,
            "win_probability_estimate": self.win_probability_estimate,
            "llm_response": self.llm_response,
            "created_at": self.created_at,
        }


def migrate_etf_tables(db) -> bool:
    """Create ETF Intelligence tables. Returns True if created, False if already existed."""
    cursor = db.connection.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='etf_holdings_snapshot'")
    if cursor.fetchone():
        return False

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS etf_holdings_snapshot (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            etf_symbol   TEXT    NOT NULL,
            date         TEXT    NOT NULL,
            price        REAL    DEFAULT 0,
            volume       INTEGER DEFAULT 0,
            ytd_return   REAL    DEFAULT 0,
            momentum_20d REAL    DEFAULT 0,
            volatility_20d REAL  DEFAULT 0,
            dividend_yield REAL  DEFAULT 0,
            aum          REAL    DEFAULT 0,
            sector       TEXT    DEFAULT 'Unknown',
            asset_class  TEXT    DEFAULT 'Equity',
            created_at   TEXT    DEFAULT (datetime('now')),
            UNIQUE(etf_symbol, date)
        );
        CREATE INDEX IF NOT EXISTS idx_etf_snapshot_date   ON etf_holdings_snapshot(date);
        CREATE INDEX IF NOT EXISTS idx_etf_snapshot_symbol ON etf_holdings_snapshot(etf_symbol);

        CREATE TABLE IF NOT EXISTS etf_recommendations (
            id                     INTEGER PRIMARY KEY AUTOINCREMENT,
            recommendation_date    TEXT NOT NULL,
            etf_symbol             TEXT NOT NULL,
            recommendation_type    TEXT NOT NULL,
            confidence             REAL DEFAULT 0,
            reason                 TEXT DEFAULT '',
            sector                 TEXT DEFAULT 'Unknown',
            correlation_to_portfolio REAL DEFAULT 0,
            suggested_allocation_pct REAL DEFAULT 0,
            win_probability_estimate REAL DEFAULT 0,
            llm_response           TEXT DEFAULT '{}',
            created_at             TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_etf_rec_type ON etf_recommendations(recommendation_type);
        CREATE INDEX IF NOT EXISTS idx_etf_rec_date ON etf_recommendations(recommendation_date);
    """)
    db.connection.commit()
    return True


def insert_etf_snapshot(db, snapshot: ETFSnapshot) -> bool:
    try:
        db.connection.execute(
            """INSERT OR REPLACE INTO etf_holdings_snapshot
               (etf_symbol, date, price, volume, ytd_return, momentum_20d,
                volatility_20d, dividend_yield, aum, sector, asset_class)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            snapshot.to_db_tuple(),
        )
        db.connection.commit()
        return True
    except Exception:
        return False


def insert_etf_recommendation(db, rec: ETFRecommendation) -> bool:
    try:
        db.connection.execute(
            """INSERT INTO etf_recommendations
               (recommendation_date, etf_symbol, recommendation_type, confidence, reason,
                sector, correlation_to_portfolio, suggested_allocation_pct,
                win_probability_estimate, llm_response)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            rec.to_db_tuple(),
        )
        db.connection.commit()
        return True
    except Exception:
        return False


def query_etf_snapshots(db, symbols: List[str], date: str) -> List[Dict]:
    if not symbols:
        return []
    placeholders = ",".join("?" * len(symbols))
    cursor = db.connection.execute(
        f"SELECT * FROM etf_holdings_snapshot WHERE etf_symbol IN ({placeholders}) AND date=?",
        (*symbols, date),
    )
    return [dict(row) for row in cursor.fetchall()]


def query_latest_etf_snapshot(db, symbol: str) -> Optional[Dict]:
    cursor = db.connection.execute(
        "SELECT * FROM etf_holdings_snapshot WHERE etf_symbol=? ORDER BY date DESC LIMIT 1",
        (symbol,),
    )
    row = cursor.fetchone()
    return dict(row) if row else None


def query_etf_recommendations(db, rec_type: Optional[str] = None,
                               limit: int = 20, days_back: int = 30) -> List[Dict]:
    if rec_type:
        cursor = db.connection.execute(
            """SELECT * FROM etf_recommendations
               WHERE recommendation_type=?
                 AND recommendation_date >= date('now', ? )
               ORDER BY recommendation_date DESC, confidence DESC
               LIMIT ?""",
            (rec_type, f"-{days_back} days", limit),
        )
    else:
        cursor = db.connection.execute(
            """SELECT * FROM etf_recommendations
               WHERE recommendation_date >= date('now', ?)
               ORDER BY recommendation_date DESC, confidence DESC
               LIMIT ?""",
            (f"-{days_back} days", limit),
        )
    return [dict(row) for row in cursor.fetchall()]


def query_etf_snapshot_history(db, symbol: str, days: int = 60) -> List[Dict]:
    cursor = db.connection.execute(
        """SELECT * FROM etf_holdings_snapshot
           WHERE etf_symbol=? AND date >= date('now', ?)
           ORDER BY date ASC""",
        (symbol, f"-{days} days"),
    )
    return [dict(row) for row in cursor.fetchall()]
