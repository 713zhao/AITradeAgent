"""Data models for LearningAgent - Layer 1, 2, 3 trade analysis results."""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
import json


class PatternType(str, Enum):
    """Trade pattern classifications from LLM analysis."""
    CONTINUATION_BREAKOUT = "continuation_breakout"
    REVERSAL = "reversal"
    MEAN_REVERSION = "mean_reversion"
    MOMENTUM = "momentum"
    SUPPORT_RESISTANCE = "support_resistance"
    TECHNICAL_BOUNCE = "technical_bounce"
    FUNDAMENTAL_DRIVEN = "fundamental_driven"
    MACRO_DRIVEN = "macro_driven"
    SENTIMENT_DRIVEN = "sentiment_driven"
    EARNINGS_PLAY = "earnings_play"
    UNKNOWN = "unknown"


@dataclass
class TradeAnalysisLayer1:
    """
    Layer 1 Analysis Result: Real-time post-trade pattern analysis using LLM.
    """
    trade_id: str
    symbol: str
    entry_score: float  # 0-10
    skill_vs_luck_ratio: float  # 0-1.0
    pattern_type: str  # PatternType enum value
    mistakes: List[str] = field(default_factory=list)
    psychological_notes: List[str] = field(default_factory=list)
    recommendations: List[Dict[str, Any]] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    llm_response: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        data = asdict(self)
        data['created_at'] = self.created_at.isoformat()
        data['llm_response'] = json.dumps(self.llm_response) if self.llm_response else "{}"
        return data
    
    def to_db_tuple(self) -> tuple:
        """Convert to database insertion tuple."""
        return (
            self.trade_id,
            self.symbol,
            round(self.entry_score, 2),
            round(self.skill_vs_luck_ratio, 3),
            self.pattern_type,
            json.dumps(self.mistakes),
            json.dumps(self.psychological_notes),
            json.dumps(self.recommendations),
            json.dumps(self.tags),
            json.dumps(self.llm_response),
            self.created_at.isoformat()
        )


@dataclass
class TradeAnalysisLayer2:
    """Layer 2 Analysis Result: Weekly pattern aggregation and root cause analysis."""
    pattern_type: str
    week_ending: datetime
    sample_size: int
    win_rate: float
    avg_win_pct: float
    avg_loss_pct: float
    profit_factor: float
    expectancy: float
    root_causes: List[str] = field(default_factory=list)
    success_factors: List[str] = field(default_factory=list)
    recommendations: List[Dict[str, Any]] = field(default_factory=list)
    llm_response: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_db_tuple(self) -> tuple:
        """Convert to database insertion tuple."""
        return (
            self.pattern_type,
            self.week_ending.isoformat(),
            self.sample_size,
            round(self.win_rate, 2),
            round(self.avg_win_pct, 4),
            round(self.avg_loss_pct, 4),
            round(self.profit_factor, 3),
            round(self.expectancy, 4),
            json.dumps(self.root_causes),
            json.dumps(self.success_factors),
            json.dumps(self.recommendations),
            json.dumps(self.llm_response),
            self.created_at.isoformat()
        )


@dataclass  
class TradeAnalysisLayer3:
    """Layer 3 Analysis Result: Parameter optimization recommendations."""
    optimization_id: str
    parameter_set: Dict[str, Any]
    expected_improvement_pct: float
    confidence_score: float  # 0-1.0
    trades_backtested: int
    win_rate_before: float
    win_rate_after: float
    profit_factor_before: float
    profit_factor_after: float
    risk_assessment: str
    rollback_conditions: List[str] = field(default_factory=list)
    llm_response: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_db_tuple(self) -> tuple:
        """Convert to database insertion tuple."""
        return (
            self.optimization_id,
            json.dumps(self.parameter_set),
            round(self.expected_improvement_pct, 2),
            round(self.confidence_score, 3),
            self.trades_backtested,
            round(self.win_rate_before, 2),
            round(self.win_rate_after, 2),
            round(self.profit_factor_before, 3),
            round(self.profit_factor_after, 3),
            self.risk_assessment,
            json.dumps(self.rollback_conditions),
            json.dumps(self.llm_response),
            self.created_at.isoformat()
        )


# ==================== MIGRATION HELPER FUNCTIONS ====================

def migrate_learning_layer1(db) -> bool:
    """Initialize Layer 1 trade_analysis table if it doesn't exist."""
    try:
        cursor = db.connection.cursor()
        
        # Check if table already exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='trade_analysis'"
        )
        if cursor.fetchone() is not None:
            return True  # Already exists
        
        # Create table
        cursor.execute('''
            CREATE TABLE trade_analysis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id TEXT NOT NULL UNIQUE,
                symbol TEXT NOT NULL,
                entry_score REAL NOT NULL CHECK (entry_score >= 0 AND entry_score <= 10),
                skill_vs_luck_ratio REAL NOT NULL CHECK (skill_vs_luck_ratio >= 0 AND skill_vs_luck_ratio <= 1),
                pattern_type TEXT NOT NULL,
                mistakes TEXT NOT NULL DEFAULT '[]',
                psychological_notes TEXT NOT NULL DEFAULT '[]',
                recommendations TEXT NOT NULL DEFAULT '[]',
                tags TEXT NOT NULL DEFAULT '[]',
                llm_response TEXT NOT NULL DEFAULT '{}',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create indices
        cursor.execute('CREATE INDEX idx_trade_analysis_trade_id ON trade_analysis(trade_id)')
        cursor.execute('CREATE INDEX idx_trade_analysis_symbol ON trade_analysis(symbol)')
        cursor.execute('CREATE INDEX idx_trade_analysis_pattern ON trade_analysis(pattern_type)')
        cursor.execute('CREATE INDEX idx_trade_analysis_created ON trade_analysis(created_at)')
        
        db.connection.commit()
        return True
    except Exception as e:
        print(f"Layer 1 migration failed: {e}")
        return False


def insert_trade_analysis_layer1(db, analysis: TradeAnalysisLayer1) -> bool:
    """Insert a Layer 1 trade analysis result into the database."""
    try:
        cursor = db.connection.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO trade_analysis (
                trade_id, symbol, entry_score, skill_vs_luck_ratio, pattern_type,
                mistakes, psychological_notes, recommendations, tags, llm_response, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', analysis.to_db_tuple())
        db.connection.commit()
        return True
    except Exception as e:
        print(f"Failed to insert trade analysis: {e}")
        return False


def get_trade_analysis_layer1(db, trade_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a Layer 1 trade analysis by trade_id."""
    try:
        cursor = db.connection.cursor()
        cursor.execute(
            '''SELECT * FROM trade_analysis WHERE trade_id = ?''',
            (trade_id,)
        )
        row = cursor.fetchone()
        if row is None:
            return None
        
        # Convert row to dict
        return {
            'id': row[0],
            'trade_id': row[1],
            'symbol': row[2],
            'entry_score': row[3],
            'skill_vs_luck_ratio': row[4],
            'pattern_type': row[5],
            'mistakes': json.loads(row[6]),
            'psychological_notes': json.loads(row[7]),
            'recommendations': json.loads(row[8]),
            'tags': json.loads(row[9]),
            'llm_response': json.loads(row[10]),
            'created_at': row[11]
        }
    except Exception as e:
        print(f"Failed to retrieve trade analysis: {e}")
        return None


def query_trade_analysis_by_symbol(db, symbol: str, limit: int = 100) -> List[Dict[str, Any]]:
    """Query all trade analyses for a given symbol."""
    try:
        cursor = db.connection.cursor()
        cursor.execute(
            '''SELECT * FROM trade_analysis WHERE symbol = ? ORDER BY created_at DESC LIMIT ?''',
            (symbol, limit)
        )
        rows = cursor.fetchall()
        
        results = []
        for row in rows:
            results.append({
                'id': row[0],
                'trade_id': row[1],
                'symbol': row[2],
                'entry_score': row[3],
                'skill_vs_luck_ratio': row[4],
                'pattern_type': row[5],
                'mistakes': json.loads(row[6]),
                'psychological_notes': json.loads(row[7]),
                'recommendations': json.loads(row[8]),
                'tags': json.loads(row[9]),
                'llm_response': json.loads(row[10]),
                'created_at': row[11]
            })
        
        return results
    except Exception as e:
        print(f"Failed to query trade analyses: {e}")
        return []
