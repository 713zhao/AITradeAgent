"""Logging configuration and utilities"""
import logging
import sqlite3
from pathlib import Path
from datetime import datetime
from .config import Config
import json

def setup_logger(name: str) -> logging.Logger:
    """Configure logger for finance service"""
    logger = logging.getLogger(name)
    
    if logger.handlers:
        return logger
    
    logger.setLevel(logging.DEBUG)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_format = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)
    
    return logger

class RunLogger:
    """Log trading runs to database"""
    
    def __init__(self):
        self.db_path = Config.RUNS_FILE
        self._init_db()
    
    def _init_db(self):
        """Initialize runs database"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS runs (
                    task_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    symbol TEXT,
                    prompt_hash TEXT,
                    decision_json TEXT,
                    approval_id TEXT,
                    approval_status TEXT,
                    execution_status TEXT,
                    created_at REAL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT,
                    symbol TEXT,
                    action TEXT,
                    qty REAL,
                    price REAL,
                    timestamp TEXT,
                    approval_id TEXT,
                    executed_at REAL,
                    FOREIGN KEY (task_id) REFERENCES runs(task_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    cash REAL,
                    equity REAL,
                    total_value REAL,
                    positions_json TEXT,
                    created_at REAL
                )
            """)
            conn.commit()
    
    def log_run(self, task_id: str, symbol: str, decision_json: str, 
                prompt_hash: str = ""):
        """Log an analysis run"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO runs 
                (task_id, timestamp, symbol, prompt_hash, decision_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (task_id, datetime.utcnow().isoformat(), symbol, 
                  prompt_hash, decision_json, datetime.utcnow().timestamp()))
            conn.commit()
    
    def log_trade(self, task_id: str, symbol: str, action: str, 
                 qty: float, price: float, approval_id: str = ""):
        """Log a trade execution"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO trades 
                (task_id, symbol, action, qty, price, timestamp, approval_id, executed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (task_id, symbol, action, qty, price,
                  datetime.utcnow().isoformat(), approval_id, 
                  datetime.utcnow().timestamp()))
            conn.commit()
    
    def log_portfolio_snapshot(self, cash: float, equity: float, 
                               positions_json: str):
        """Log portfolio state"""
        total_value = cash + equity
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO portfolio_snapshots 
                (timestamp, cash, equity, total_value, positions_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (datetime.utcnow().isoformat(), cash, equity, total_value,
                  positions_json, datetime.utcnow().timestamp()))
            conn.commit()
    
    def get_run(self, task_id: str):
        """Retrieve logged run"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM runs WHERE task_id = ?", (task_id,)
            )
            return cursor.fetchone()
    
    def get_trades(self, task_id: str):
        """Retrieve trades for a run"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM trades WHERE task_id = ? ORDER BY executed_at",
                (task_id,)
            )
            return cursor.fetchall()
