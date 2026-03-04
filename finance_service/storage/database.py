"""SQLite Database Management with schema initialization"""
import sqlite3
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
import json
import threading

logger = logging.getLogger(__name__)


class Database:
    """SQLite database management with schema"""
    
    def __init__(self, db_path: str = "storage/portfolio.sqlite"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self._local = threading.local()  # Thread-local storage for connections
        self._init_lock = threading.Lock()
        self._schema_version = 1
        
        logger.info(f"Database initialized: {self.db_path}")
    
    @property
    def connection(self) -> sqlite3.Connection:
        """Get thread-local database connection"""
        if not hasattr(self._local, 'connection'):
            self._local.connection = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
                timeout=10.0
            )
            self._local.connection.row_factory = sqlite3.Row
        
        return self._local.connection
    
    def initialize_schema(self) -> bool:
        """Initialize database schema"""
        with self._init_lock:
            cursor = self.connection.cursor()
            
            try:
                # Check if schema exists
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='positions'"
                )
                
                if cursor.fetchone() is None:
                    logger.info("Creating database schema...")
                    self._create_schema(cursor)
                    self.connection.commit()
                    logger.info("Database schema created successfully")
                    return True
                else:
                    logger.info("Database schema already exists")
                    return False
            
            except Exception as e:
                logger.error(f"Error initializing schema: {e}")
                self.connection.rollback()
                raise
    
    def _create_schema(self, cursor: sqlite3.Cursor) -> None:
        """Create all tables"""
        
        # Positions table
        cursor.execute('''
            CREATE TABLE positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
                quantity REAL NOT NULL,
                entry_price REAL NOT NULL,
                entry_date TIMESTAMP NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('OPEN', 'CLOSED')),
                exit_price REAL,
                exit_date TIMESTAMP,
                pnl REAL,
                pnl_pct REAL,
                stop_loss REAL,
                take_profit REAL,
                confidence REAL,
                signals TEXT,
                notes TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Trades table (logs all executions)
        cursor.execute('''
            CREATE TABLE trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
                quantity REAL NOT NULL,
                price REAL NOT NULL,
                commission REAL DEFAULT 0,
                trade_value REAL,
                timestamp TIMESTAMP NOT NULL,
                position_id INTEGER REFERENCES positions(id),
                confidence REAL,
                signals TEXT,
                approval_status TEXT CHECK (approval_status IN ('AUTO', 'APPROVED', 'REJECTED', 'PENDING')),
                approval_time TIMESTAMP,
                execution_report TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Portfolio snapshots (for equity curve)
        cursor.execute('''
            CREATE TABLE portfolio_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_date TIMESTAMP NOT NULL,
                cash REAL NOT NULL,
                positions_value REAL NOT NULL,
                total_equity REAL NOT NULL,
                total_return_pct REAL,
                daily_return_pct REAL,
                max_drawdown_pct REAL,
                open_trades_count INTEGER,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Configuration audit log
        cursor.execute('''
            CREATE TABLE config_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                config_section TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT,
                changed_by TEXT DEFAULT 'system',
                changed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Backtest results
        cursor.execute('''
            CREATE TABLE backtest_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_name TEXT,
                start_date TIMESTAMP NOT NULL,
                end_date TIMESTAMP NOT NULL,
                initial_capital REAL NOT NULL,
                final_equity REAL NOT NULL,
                total_return_pct REAL,
                cagr_pct REAL,
                max_drawdown_pct REAL,
                sharpe_ratio REAL,
                sortino_ratio REAL,
                win_rate_pct REAL,
                profit_factor REAL,
                total_trades INTEGER,
                winning_trades INTEGER,
                losing_trades INTEGER,
                avg_win REAL,
                avg_loss REAL,
                config_json TEXT,
                results_json TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Analysis results cache
        cursor.execute('''
            CREATE TABLE analysis_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                analysis_date TIMESTAMP NOT NULL,
                rsi REAL,
                macd REAL,
                macd_signal REAL,
                sma20 REAL,
                sma50 REAL,
                sma200 REAL,
                atr REAL,
                bollinger_upper REAL,
                bollinger_middle REAL,
                bollinger_lower REAL,
                stochastic_k REAL,
                stochastic_d REAL,
                decision_json TEXT,
                confidence REAL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, analysis_date)
            )
        ''')
        
        # Event log (for debugging)
        cursor.execute('''
            CREATE TABLE event_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                event_data TEXT,
                source TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create indexes for common queries
        cursor.execute('CREATE INDEX idx_positions_symbol ON positions(symbol)')
        cursor.execute('CREATE INDEX idx_positions_status ON positions(status)')
        cursor.execute('CREATE INDEX idx_trades_symbol ON trades(symbol)')
        cursor.execute('CREATE INDEX idx_trades_timestamp ON trades(timestamp)')
        cursor.execute('CREATE INDEX idx_analysis_symbol ON analysis_cache(symbol)')
        cursor.execute('CREATE INDEX idx_portfolio_snapshots_date ON portfolio_snapshots(snapshot_date)')
    
    def insert_position(self, position: Dict[str, Any]) -> int:
        """Insert a new position"""
        cursor = self.connection.cursor()
        
        cursor.execute('''
            INSERT INTO positions (
                symbol, side, quantity, entry_price, entry_date, status,
                stop_loss, take_profit, confidence, signals, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            position['symbol'],
            position['side'],
            position['quantity'],
            position['entry_price'],
            position['entry_date'],
            'OPEN',
            position.get('stop_loss'),
            position.get('take_profit'),
            position.get('confidence'),
            json.dumps(position.get('signals', [])),
            position.get('notes', '')
        ))
        
        self.connection.commit()
        return cursor.lastrowid
    
    def insert_trade(self, trade: Dict[str, Any]) -> int:
        """Insert a trade execution"""
        cursor = self.connection.cursor()
        
        cursor.execute('''
            INSERT INTO trades (
                symbol, side, quantity, price, commission, trade_value, timestamp,
                confidence, signals, approval_status, execution_report
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            trade['symbol'],
            trade['side'],
            trade['quantity'],
            trade['price'],
            trade.get('commission', 0),
            trade.get('trade_value'),
            trade['timestamp'],
            trade.get('confidence'),
            json.dumps(trade.get('signals', [])),
            trade.get('approval_status', 'PENDING'),
            json.dumps(trade.get('execution_report', {}))
        ))
        
        self.connection.commit()
        return cursor.lastrowid
    
    def insert_portfolio_snapshot(self, snapshot: Dict[str, Any]) -> int:
        """Insert portfolio snapshot"""
        cursor = self.connection.cursor()
        
        cursor.execute('''
            INSERT INTO portfolio_snapshots (
                snapshot_date, cash, positions_value, total_equity,
                total_return_pct, daily_return_pct, max_drawdown_pct, open_trades_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            snapshot['snapshot_date'],
            snapshot['cash'],
            snapshot['positions_value'],
            snapshot['total_equity'],
            snapshot.get('total_return_pct'),
            snapshot.get('daily_return_pct'),
            snapshot.get('max_drawdown_pct'),
            snapshot.get('open_trades_count', 0)
        ))
        
        self.connection.commit()
        return cursor.lastrowid
    
    def get_open_positions(self, symbol: Optional[str] = None) -> List[Dict]:
        """Get all open positions"""
        cursor = self.connection.cursor()
        
        if symbol:
            cursor.execute('SELECT * FROM positions WHERE status = ? AND symbol = ?', ('OPEN', symbol))
        else:
            cursor.execute('SELECT * FROM positions WHERE status = ?', ('OPEN',))
        
        return [dict(row) for row in cursor.fetchall()]
    
    def get_trade_history(self, symbol: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """Get trade history"""
        cursor = self.connection.cursor()
        
        if symbol:
            cursor.execute(
                'SELECT * FROM trades WHERE symbol = ? ORDER BY timestamp DESC LIMIT ?',
                (symbol, limit)
            )
        else:
            cursor.execute('SELECT * FROM trades ORDER BY timestamp DESC LIMIT ?', (limit,))
        
        return [dict(row) for row in cursor.fetchall()]
    
    def get_portfolio_snapshots(self, limit: int = 100) -> List[Dict]:
        """Get portfolio snapshots"""
        cursor = self.connection.cursor()
        cursor.execute(
            'SELECT * FROM portfolio_snapshots ORDER BY snapshot_date DESC LIMIT ?',
            (limit,)
        )
        
        return [dict(row) for row in cursor.fetchall()]
    
    def close(self):
        """Close database connection"""
        if hasattr(self._local, 'connection'):
            self._local.connection.close()
            delattr(self._local, 'connection')
    
    def __repr__(self) -> str:
        return f"Database(path={self.db_path})"


# Global database instances
_portfolio_db: Optional[Database] = None
_cache_db: Optional[Database] = None
_backtest_db: Optional[Database] = None


def get_portfolio_db() -> Database:
    """Get portfolio database (singleton)"""
    global _portfolio_db
    if _portfolio_db is None:
        _portfolio_db = Database("storage/portfolio.sqlite")
        _portfolio_db.initialize_schema()
    return _portfolio_db


def get_cache_db() -> Database:
    """Get cache database (singleton)"""
    global _cache_db
    if _cache_db is None:
        _cache_db = Database("storage/cache.sqlite")
        _cache_db.initialize_schema()
    return _cache_db


def get_backtest_db() -> Database:
    """Get backtest database (singleton)"""
    global _backtest_db
    if _backtest_db is None:
        _backtest_db = Database("storage/backtest.sqlite")
        _backtest_db.initialize_schema()
    return _backtest_db
