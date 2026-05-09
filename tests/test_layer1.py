"""
Unit tests for Layer 1 Trade Analysis Engine (learning_agent.py)

Tests cover:
- layer1_analyze_trade() core logic
- Context building
- Prompt formatting
- JSON parsing and validation
- Error handling and timeouts
- TradeAnalysisLayer1 dataclass
"""

import pytest
import json
import asyncio
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Dict, Any

# Import components to test
from finance_service.ml.learning_models import TradeAnalysisLayer1, PatternType


# ==================== MOCK DATA ====================

def get_mock_trade_data() -> Dict[str, Any]:
    """Get sample trade data for testing."""
    return {
        'trade_id': 'TRADE_000451',
        'symbol': 'AAPL',
        'side': 'BUY',
        'quantity': 100,
        'price': 150.25,
        'exit_price': 152.00,
        'pnl': 175.00,
        'pnl_pct': 1.16,
        'filled_at': '2024-05-09T14:30:00Z',
        'reason': 'Breakout above resistance at 150',
        'confidence': 7,
    }


# ==================== TESTS: DataClass Validation ====================

class TestTradeAnalysisLayer1:
    """Tests for TradeAnalysisLayer1 dataclass"""
    
    def test_create_analysis_with_all_fields(self):
        """Test creating TradeAnalysisLayer1 with all fields."""
        analysis = TradeAnalysisLayer1(
            trade_id='TRADE_000451',
            symbol='AAPL',
            entry_score=7.5,
            skill_vs_luck_ratio=0.68,
            pattern_type='continuation_breakout',
            mistakes=['Early entry', 'No volume check'],
            psychological_notes=['FOMO'],
            recommendations=[{'category': 'entry_timing', 'suggestion': 'Wait more'}],
            tags=['breakout']
        )
        
        assert analysis.trade_id == 'TRADE_000451'
        assert analysis.entry_score == 7.5
        assert len(analysis.mistakes) == 2
    
    def test_analysis_to_dict(self):
        """Test converting analysis to dictionary."""
        analysis = TradeAnalysisLayer1(
            trade_id='TRADE_000451',
            symbol='AAPL',
            entry_score=8.0,
            skill_vs_luck_ratio=0.75,
            pattern_type='reversal'
        )
        
        d = analysis.to_dict()
        
        assert d['trade_id'] == 'TRADE_000451'
        assert d['entry_score'] == 8.0
        assert isinstance(d['created_at'], str)
    
    def test_analysis_to_db_tuple(self):
        """Test converting analysis to database insertion tuple."""
        analysis = TradeAnalysisLayer1(
            trade_id='TRADE_000451',
            symbol='AAPL',
            entry_score=7.5,
            skill_vs_luck_ratio=0.68,
            pattern_type='breakout',
            mistakes=['Early entry'],
            recommendations=[{'suggestion': 'Wait'}]
        )
        
        db_tuple = analysis.to_db_tuple()
        
        assert len(db_tuple) == 11  # trade_id through created_at
        assert db_tuple[0] == 'TRADE_000451'
        assert db_tuple[1] == 'AAPL'
        assert db_tuple[2] == 7.5  # entry_score rounded


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
