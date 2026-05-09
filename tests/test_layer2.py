"""Unit tests for Layer 2 weekly pattern analysis."""
import pytest
import sys
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from finance_service.ml.learning_models import (
    TradeAnalysisLayer2,
    PatternType,
    aggregate_trades_by_pattern,
    query_trade_analysis_layer2_recent
)


class TestTradeAnalysisLayer2:
    """Test Layer 2 analysis dataclass."""
    
    def test_create_layer2_analysis(self):
        """Test creating Layer 2 analysis object."""
        analysis = TradeAnalysisLayer2(
            pattern_type=PatternType.MOMENTUM,
            week_ending=datetime(2026, 5, 9),
            sample_size=5,
            win_rate=60.0,
            avg_win_pct=2.5,
            avg_loss_pct=-1.2,
            profit_factor=1.5,
            expectancy=1.1,
            root_causes=["False signals on high volume", "Overtrading"],
            success_factors=["Morning breakouts work better", "High IV favors entries"],
            recommendations=[
                {"action": "Add volume filter", "expected_impact": "+15% win rate", "priority": "high"}
            ]
        )
        
        assert analysis.pattern_type == PatternType.MOMENTUM
        assert analysis.sample_size == 5
        assert analysis.win_rate == 60.0
        assert analysis.profit_factor == 1.5
        assert len(analysis.root_causes) == 2
        assert len(analysis.success_factors) == 2
        assert analysis.created_at is not None
    
    def test_layer2_to_db_tuple(self):
        """Test converting Layer 2 analysis to database tuple."""
        analysis = TradeAnalysisLayer2(
            pattern_type="mean_reversion",
            week_ending=datetime(2026, 5, 9),
            sample_size=8,
            win_rate=55.5,
            avg_win_pct=1.8,
            avg_loss_pct=-0.9,
            profit_factor=2.0,
            expectancy=0.8,
            root_causes=["Entries too early", "Risk/reward off"],
            success_factors=["Works well on support bounces"]
        )
        
        db_tuple = analysis.to_db_tuple()
        
        # Should have 13 elements
        assert len(db_tuple) == 13
        assert db_tuple[0] == "mean_reversion"  # pattern_type
        assert db_tuple[2] == 8  # sample_size
        assert db_tuple[3] == 55.5  # win_rate
    
    def test_layer2_analysis_statistics(self):
        """Test Layer 2 statistics are valid."""
        analysis = TradeAnalysisLayer2(
            pattern_type=PatternType.REVERSAL,
            week_ending=datetime(2026, 5, 9),
            sample_size=3,
            win_rate=66.67,
            avg_win_pct=3.0,
            avg_loss_pct=-1.5,
            profit_factor=2.0,
            expectancy=1.5
        )
        
        # Verify statistical soundness
        assert 0 <= analysis.win_rate <= 100
        assert 0 <= analysis.profit_factor
        assert analysis.sample_size > 0
    
    def test_layer2_multiple_recommendations(self):
        """Test Layer 2 with multiple recommendations."""
        recommendations = [
            {
                "action": "Tighten stop loss",
                "expected_impact": "+20% profit factor",
                "implementation": "Backtest with 5% stops",
                "priority": "high"
            },
            {
                "action": "Filter by time of day",
                "expected_impact": "+10% win rate",
                "implementation": "Trade only 9:30-14:00 ET",
                "priority": "medium"
            }
        ]
        
        analysis = TradeAnalysisLayer2(
            pattern_type=PatternType.SUPPORT_RESISTANCE,
            week_ending=datetime(2026, 5, 9),
            sample_size=12,
            win_rate=52.0,
            avg_win_pct=2.0,
            avg_loss_pct=-1.8,
            profit_factor=1.44,
            expectancy=0.22,
            recommendations=recommendations
        )
        
        assert len(analysis.recommendations) == 2
        assert analysis.recommendations[0]["priority"] == "high"


class TestLayer2Integration:
    """Integration tests for Layer 2."""
    
    def test_weekly_end_date_calculation(self):
        """Test calculation of week ending dates."""
        week_ending = datetime(2026, 5, 9)
        
        analysis = TradeAnalysisLayer2(
            pattern_type=PatternType.CONTINUATION_BREAKOUT,
            week_ending=week_ending,
            sample_size=1,
            win_rate=100.0,
            avg_win_pct=1.0,
            avg_loss_pct=0.0,
            profit_factor=1.0,
            expectancy=1.0
        )
        
        assert analysis.week_ending == week_ending
        assert isinstance(analysis.created_at, datetime)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
