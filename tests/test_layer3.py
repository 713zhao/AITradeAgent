"""Unit tests for Layer 3 parameter optimization."""
import pytest
import sys
from pathlib import Path
from datetime import datetime
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from finance_service.ml.learning_models import TradeAnalysisLayer3


class TestTradeAnalysisLayer3:
    """Test Layer 3 optimization dataclass."""
    
    def test_create_layer3_optimization(self):
        """Test creating Layer 3 optimization object."""
        analysis = TradeAnalysisLayer3(
            optimization_id="OPT_ABC123",
            parameter_set=[
                {"parameter": "stop_loss", "change": "2% -> 1.5%"},
                {"parameter": "position_size", "change": "1% -> 0.8%"}
            ],
            expected_improvement_pct=12.5,
            confidence_score=0.75,
            trades_backtested=45,
            win_rate_before=52.0,
            win_rate_after=58.0,
            profit_factor_before=1.35,
            profit_factor_after=1.62,
            risk_assessment="MEDIUM"
        )
        
        assert analysis.optimization_id == "OPT_ABC123"
        assert len(analysis.parameter_set) == 2
        assert analysis.expected_improvement_pct == 12.5
        assert analysis.confidence_score == 0.75
        assert analysis.trades_backtested == 45
        assert 0 <= analysis.confidence_score <= 1.0
    
    def test_layer3_to_db_tuple(self):
        """Test converting Layer 3 optimization to database tuple."""
        analysis = TradeAnalysisLayer3(
            optimization_id="OPT_XYZ789",
            parameter_set=[{"param": "value"}],
            expected_improvement_pct=8.5,
            confidence_score=0.82,
            trades_backtested=60,
            win_rate_before=50.0,
            win_rate_after=54.25,
            profit_factor_before=1.22,
            profit_factor_after=1.38,
            risk_assessment="LOW",
            rollback_conditions=["win_rate < 48%", "drawdown > 15%"]
        )
        
        db_tuple = analysis.to_db_tuple()
        
        # Should have 13 elements
        assert len(db_tuple) == 13
        assert db_tuple[0] == "OPT_XYZ789"  # optimization_id
        assert db_tuple[2] == 8.5  # expected_improvement_pct
        assert db_tuple[3] == 0.82  # confidence_score
        assert db_tuple[4] == 60  # trades_backtested
    
    def test_layer3_improvement_metrics(self):
        """Test Layer 3 improvement metrics calculations."""
        analysis = TradeAnalysisLayer3(
            optimization_id="OPT_TEST",
            parameter_set=[],
            expected_improvement_pct=15.0,
            confidence_score=0.88,
            trades_backtested=100,
            win_rate_before=48.0,
            win_rate_after=55.2,
            profit_factor_before=1.15,
            profit_factor_after=1.44,
            risk_assessment="MEDIUM"
        )
        
        # Verify improvements are positive
        assert analysis.win_rate_after > analysis.win_rate_before
        assert analysis.profit_factor_after > analysis.profit_factor_before
        assert analysis.expected_improvement_pct > 0
        assert 0 < analysis.confidence_score <= 1.0
    
    def test_layer3_rollback_conditions(self):
        """Test Layer 3 with detailed rollback conditions."""
        rollback = [
            "Drop below 45% win rate for 25+ consecutive trades",
            "Max daily drawdown exceeds 8%",
            "Profit factor falls below 1.0 for any 2-week period"
        ]
        
        analysis = TradeAnalysisLayer3(
            optimization_id="OPT_SAFE",
            parameter_set=[{"param": "values"}],
            expected_improvement_pct=20.0,
            confidence_score=0.91,
            trades_backtested=200,
            win_rate_before=51.0,
            win_rate_after=61.2,
            profit_factor_before=1.29,
            profit_factor_after=1.73,
            risk_assessment="LOW",
            rollback_conditions=rollback
        )
        
        assert len(analysis.rollback_conditions) == 3
        assert all(isinstance(cond, str) for cond in analysis.rollback_conditions)
        assert "win rate" in analysis.rollback_conditions[0].lower()
    
    def test_layer3_high_confidence_optimization(self):
        """Test Layer 3 with high confidence optimization."""
        analysis = TradeAnalysisLayer3(
            optimization_id="OPT_PROVEN",
            parameter_set=[
                {"category": "Risk", "parameter": "stop_loss", "change": "2% -> 1.8%", "rationale": "Historical data shows tighter stops work"},
                {"category": "Entry", "parameter": "confirmation_count", "change": "2 -> 3", "rationale": "Reduces false signals by 12%"}
            ],
            expected_improvement_pct=18.5,
            confidence_score=0.95,
            trades_backtested=150,
            win_rate_before=53.0,
            win_rate_after=62.8,
            profit_factor_before=1.42,
            profit_factor_after=1.89,
            risk_assessment="LOW"
        )
        
        # High confidence and good metrics
        assert analysis.confidence_score >= 0.9
        assert analysis.expected_improvement_pct >= 15.0
        assert analysis.profit_factor_after >= 1.5
    
    def test_layer3_conservative_optimization(self):
        """Test Layer 3 with conservative improvements."""
        analysis = TradeAnalysisLayer3(
            optimization_id="OPT_CONSERVATIVE",
            parameter_set=[{"param": "tweak"}],
            expected_improvement_pct=3.5,
            confidence_score=0.65,
            trades_backtested=40,
            win_rate_before=49.0,
            win_rate_after=50.7,
            profit_factor_before=0.98,
            profit_factor_after=1.01,
            risk_assessment="HIGH"
        )
        
        # Lower improvements with lower confidence
        assert 0 < analysis.expected_improvement_pct < 10.0
        assert 0.5 <= analysis.confidence_score < 0.8
        assert analysis.risk_assessment == "HIGH"


class TestLayer3Integration:
    """Integration tests for Layer 3."""
    
    def test_layer3_optimization_workflow(self):
        """Test complete Layer 3 optimization workflow."""
        # Create optimization
        analysis = TradeAnalysisLayer3(
            optimization_id="OPT_WORKFLOW",
            parameter_set=[
                {"parameter": "entry_signal", "change": "Add volume filter"}
            ],
            expected_improvement_pct=10.0,
            confidence_score=0.78,
            trades_backtested=80,
            win_rate_before=51.0,
            win_rate_after=56.1,
            profit_factor_before=1.31,
            profit_factor_after=1.44,
            risk_assessment="MEDIUM",
            rollback_conditions=["win_rate < 50%"],
            llm_response={
                "optimization_name": "Volume Confirmation Filter",
                "parameter_changes": [{"parameter": "entry_signal"}],
                "coaching_notes": "Volume confirmation reduces fake breakouts"
            }
        )
        
        # Verify workflow
        assert analysis.optimization_id == "OPT_WORKFLOW"
        assert isinstance(analysis.llm_response, dict)
        assert "optimization_name" in analysis.llm_response
        
        # Convert to DB tuple
        db_tuple = analysis.to_db_tuple()
        assert db_tuple[0] == "OPT_WORKFLOW"
    
    def test_layer3_multi_parameter_optimization(self):
        """Test Layer 3 with multiple parameter changes."""
        changes = [
            {
                "category": "Entry",
                "parameter": "entry_confirmation",
                "change": "2 -> 3 indicators",
                "expected_impact": "+8% win rate"
            },
            {
                "category": "Risk",
                "parameter": "position_size",
                "change": "1.0% -> 0.8% risk",
                "expected_impact": "-15% max drawdown"
            },
            {
                "category": "Pattern",
                "parameter": "pattern_filter",
                "change": "Add momentum filter",
                "expected_impact": "+12% profit factor"
            }
        ]
        
        analysis = TradeAnalysisLayer3(
            optimization_id="OPT_MULTI",
            parameter_set=changes,
            expected_improvement_pct=22.0,
            confidence_score=0.85,
            trades_backtested=250,
            win_rate_before=50.0,
            win_rate_after=59.0,
            profit_factor_before=1.25,
            profit_factor_after=1.56,
            risk_assessment="MEDIUM"
        )
        
        assert len(analysis.parameter_set) == 3
        assert all("parameter" in p or "change" in p for p in analysis.parameter_set)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
