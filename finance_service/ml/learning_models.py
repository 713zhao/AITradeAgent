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


# ==================== LAYER 2: WEEKLY PATTERN ANALYSIS ====================

def migrate_learning_layer2(db) -> bool:
    """Ensure trade_analysis_layer2 table exists with proper schema."""
    try:
        cursor = db.connection.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trade_analysis_layer2 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_type TEXT NOT NULL,
                week_ending TEXT NOT NULL,
                sample_size INTEGER NOT NULL,
                win_rate REAL NOT NULL CHECK (win_rate >= 0 AND win_rate <= 100),
                avg_win_pct REAL NOT NULL,
                avg_loss_pct REAL NOT NULL,
                profit_factor REAL NOT NULL,
                expectancy REAL NOT NULL,
                root_causes TEXT NOT NULL DEFAULT '[]',
                success_factors TEXT NOT NULL DEFAULT '[]',
                recommendations TEXT NOT NULL DEFAULT '[]',
                llm_response TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(pattern_type, week_ending)
            )
        ''')
        
        # Create indexes for efficient queries
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_layer2_pattern ON trade_analysis_layer2(pattern_type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_layer2_week ON trade_analysis_layer2(week_ending)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_layer2_created ON trade_analysis_layer2(created_at)')
        
        db.connection.commit()
        print("✅ Layer 2 migration successful")
        return True
    except Exception as e:
        print(f"⚠️ Layer 2 migration error: {e}")
        return False


def insert_trade_analysis_layer2(db, analysis: TradeAnalysisLayer2) -> bool:
    """Insert Layer 2 analysis result into database."""
    try:
        cursor = db.connection.cursor()
        data = analysis.to_db_tuple()
        
        cursor.execute('''
            INSERT OR REPLACE INTO trade_analysis_layer2
            (pattern_type, week_ending, sample_size, win_rate, avg_win_pct, avg_loss_pct,
             profit_factor, expectancy, root_causes, success_factors, recommendations, llm_response, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', data)
        
        db.connection.commit()
        print(f"✅ Layer 2 analysis inserted: {analysis.pattern_type} for week {analysis.week_ending.isoformat()}")
        return True
    except Exception as e:
        print(f"❌ Failed to insert Layer 2 analysis: {e}")
        return False


def get_trade_analysis_layer2(db, pattern_type: str, week_ending_str: str) -> Optional[Dict[str, Any]]:
    """Retrieve Layer 2 analysis for specific pattern and week."""
    try:
        cursor = db.connection.cursor()
        cursor.execute('''
            SELECT id, pattern_type, week_ending, sample_size, win_rate, avg_win_pct, 
                   avg_loss_pct, profit_factor, expectancy, root_causes, success_factors,
                   recommendations, llm_response, created_at
            FROM trade_analysis_layer2
            WHERE pattern_type = ? AND week_ending = ?
        ''', (pattern_type, week_ending_str))
        
        row = cursor.fetchone()
        if not row:
            return None
        
        return {
            'id': row[0],
            'pattern_type': row[1],
            'week_ending': row[2],
            'sample_size': row[3],
            'win_rate': row[4],
            'avg_win_pct': row[5],
            'avg_loss_pct': row[6],
            'profit_factor': row[7],
            'expectancy': row[8],
            'root_causes': json.loads(row[9]),
            'success_factors': json.loads(row[10]),
            'recommendations': json.loads(row[11]),
            'llm_response': json.loads(row[12]),
            'created_at': row[13]
        }
    except Exception as e:
        print(f"Failed to retrieve Layer 2 analysis: {e}")
        return None


def query_trade_analysis_layer2_recent(db, days: int = 30, min_sample_size: int = 3) -> List[Dict[str, Any]]:
    """Query recent Layer 2 analyses with sufficient statistics."""
    try:
        cursor = db.connection.cursor()
        cursor.execute('''
            SELECT pattern_type, week_ending, sample_size, win_rate, avg_win_pct, 
                   avg_loss_pct, profit_factor, expectancy, root_causes, success_factors,
                   recommendations, llm_response, created_at
            FROM trade_analysis_layer2
            WHERE datetime(created_at) > datetime('now', ? || ' days')
            AND sample_size >= ?
            ORDER BY created_at DESC
        ''', (f'-{days}', min_sample_size))
        
        rows = cursor.fetchall()
        results = []
        for row in rows:
            results.append({
                'pattern_type': row[0],
                'week_ending': row[1],
                'sample_size': row[2],
                'win_rate': row[3],
                'avg_win_pct': row[4],
                'avg_loss_pct': row[5],
                'profit_factor': row[6],
                'expectancy': row[7],
                'root_causes': json.loads(row[8]),
                'success_factors': json.loads(row[9]),
                'recommendations': json.loads(row[10]),
                'llm_response': json.loads(row[11]),
                'created_at': row[12]
            })
        
        return results
    except Exception as e:
        print(f"Failed to query Layer 2 analyses: {e}")
        return []


def aggregate_trades_by_pattern(db, week_ending_str: str) -> Dict[str, Dict[str, Any]]:
    """
    Aggregate all Layer 1 trades from a week by pattern type.
    Returns statistics needed for Layer 2 analysis.
    """
    try:
        cursor = db.connection.cursor()
        
        # Get all trades from the week
        cursor.execute('''
            SELECT pattern_type, entry_score, skill_vs_luck_ratio, mistakes
            FROM trade_analysis
            WHERE DATE(created_at) BETWEEN 
                DATE(?, '-6 days') AND DATE(?)
            ORDER BY pattern_type
        ''', (week_ending_str, week_ending_str))
        
        rows = cursor.fetchall()
        
        # Group by pattern and calculate statistics
        pattern_stats = {}
        for row in rows:
            pattern = row[0]
            entry_score = row[1]
            skill_ratio = row[2]
            
            if pattern not in pattern_stats:
                pattern_stats[pattern] = {
                    'trades': [],
                    'count': 0,
                    'entry_scores': [],
                    'skill_ratios': [],
                    'winning': 0,
                    'losing': 0,
                    'total_profit_pct': 0.0,
                    'total_loss_pct': 0.0
                }
            
            pattern_stats[pattern]['trades'].append(row)
            pattern_stats[pattern]['count'] += 1
            pattern_stats[pattern]['entry_scores'].append(entry_score)
            pattern_stats[pattern]['skill_ratios'].append(skill_ratio)
            
            # Entry score > 6 is considered a "win", < 4 is a "loss"
            if entry_score >= 6:
                pattern_stats[pattern]['winning'] += 1
            elif entry_score < 4:
                pattern_stats[pattern]['losing'] += 1
        
        # Calculate final statistics
        aggregated = {}
        for pattern, stats in pattern_stats.items():
            count = stats['count']
            winning = stats['winning']
            losing = stats['losing']
            
            win_rate = (winning / count * 100) if count > 0 else 0
            avg_entry_score = sum(stats['entry_scores']) / count if count > 0 else 0
            avg_skill_ratio = sum(stats['skill_ratios']) / count if count > 0 else 0
            
            aggregated[pattern] = {
                'sample_size': count,
                'win_rate': round(win_rate, 2),
                'avg_entry_score': round(avg_entry_score, 2),
                'avg_skill_ratio': round(avg_skill_ratio, 3),
                'winning_trades': winning,
                'losing_trades': losing,
                'trades': stats['trades']
            }
        
        return aggregated
    except Exception as e:
        print(f"Failed to aggregate trades: {e}")
        return {}


# ==================== LAYER 3: PARAMETER OPTIMIZATION ====================

def migrate_learning_layer3(db) -> bool:
    """Ensure trade_analysis_layer3 table exists with proper schema."""
    try:
        cursor = db.connection.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trade_analysis_layer3 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                optimization_id TEXT NOT NULL UNIQUE,
                parameter_set TEXT NOT NULL,
                expected_improvement_pct REAL NOT NULL CHECK (expected_improvement_pct >= 0),
                confidence_score REAL NOT NULL CHECK (confidence_score >= 0 AND confidence_score <= 1),
                trades_backtested INTEGER NOT NULL,
                win_rate_before REAL NOT NULL,
                win_rate_after REAL NOT NULL,
                profit_factor_before REAL NOT NULL,
                profit_factor_after REAL NOT NULL,
                risk_assessment TEXT NOT NULL,
                rollback_conditions TEXT NOT NULL DEFAULT '[]',
                llm_response TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'active', 'tested', 'rolled_back'))
            )
        ''')
        
        # Create indexes for efficient queries
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_layer3_optimization ON trade_analysis_layer3(optimization_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_layer3_created ON trade_analysis_layer3(created_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_layer3_status ON trade_analysis_layer3(status)')
        
        db.connection.commit()
        print("✅ Layer 3 migration successful")
        return True
    except Exception as e:
        print(f"⚠️  Layer 3 migration error: {e}")
        return False


def insert_trade_analysis_layer3(db, analysis: TradeAnalysisLayer3) -> bool:
    """Insert Layer 3 optimization result into database."""
    try:
        cursor = db.connection.cursor()
        data = analysis.to_db_tuple()
        
        cursor.execute('''
            INSERT OR REPLACE INTO trade_analysis_layer3
            (optimization_id, parameter_set, expected_improvement_pct, confidence_score, 
             trades_backtested, win_rate_before, win_rate_after, profit_factor_before, 
             profit_factor_after, risk_assessment, rollback_conditions, llm_response, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', data)
        
        db.connection.commit()
        print(f"✅ Layer 3 optimization inserted: {analysis.optimization_id}")
        return True
    except Exception as e:
        print(f"❌ Failed to insert Layer 3 optimization: {e}")
        return False


def get_trade_analysis_layer3(db, optimization_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve Layer 3 optimization by ID."""
    try:
        cursor = db.connection.cursor()
        cursor.execute('''
            SELECT id, optimization_id, parameter_set, expected_improvement_pct, confidence_score,
                   trades_backtested, win_rate_before, win_rate_after, profit_factor_before,
                   profit_factor_after, risk_assessment, rollback_conditions, llm_response, created_at
            FROM trade_analysis_layer3
            WHERE optimization_id = ?
        ''', (optimization_id,))
        
        row = cursor.fetchone()
        if not row:
            return None
        
        return {
            'id': row[0],
            'optimization_id': row[1],
            'parameter_set': json.loads(row[2]),
            'expected_improvement_pct': row[3],
            'confidence_score': row[4],
            'trades_backtested': row[5],
            'win_rate_before': row[6],
            'win_rate_after': row[7],
            'profit_factor_before': row[8],
            'profit_factor_after': row[9],
            'risk_assessment': row[10],
            'rollback_conditions': json.loads(row[11]),
            'llm_response': json.loads(row[12]),
            'created_at': row[13]
        }
    except Exception as e:
        print(f"Failed to retrieve Layer 3 optimization: {e}")
        return None


def query_trade_analysis_layer3_active(db) -> List[Dict[str, Any]]:
    """Query all active Layer 3 optimizations."""
    try:
        cursor = db.connection.cursor()
        cursor.execute('''
            SELECT optimization_id, parameter_set, expected_improvement_pct, confidence_score,
                   win_rate_before, win_rate_after, profit_factor_before, profit_factor_after
            FROM trade_analysis_layer3
            WHERE status = 'active'
            ORDER BY created_at DESC
        ''')
        
        rows = cursor.fetchall()
        results = []
        for row in rows:
            results.append({
                'optimization_id': row[0],
                'parameter_set': json.loads(row[1]),
                'expected_improvement_pct': row[2],
                'confidence_score': row[3],
                'win_rate_before': row[4],
                'win_rate_after': row[5],
                'profit_factor_before': row[6],
                'profit_factor_after': row[7]
            })
        
        return results
    except Exception as e:
        print(f"Failed to query Layer 3 optimizations: {e}")
        return []
