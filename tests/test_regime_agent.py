"""Tests for RegimeAgent."""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime
from finance_service.agents.regime_agent import RegimeAgent, MarketRegime
from finance_service.core.yaml_config import YAMLConfigEngine


class TestMarketRegime:
    """Test MarketRegime dataclass"""

    def test_create(self):
        regime = MarketRegime(
            regime="trending_bullish",
            confidence=0.85,
            description="Test",
            timestamp=datetime.now(),
        )
        assert regime.regime == "trending_bullish"
        assert regime.confidence == 0.85


class TestRegimeAgent:
    """Test RegimeAgent functionality"""

    @pytest.fixture
    def config_engine(self, tmp_path):
        """Create a minimal config engine"""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "config.yaml"
        config_file.write_text("llm:\n  enabled: false\n")
        engine = YAMLConfigEngine(config_dir=str(config_dir), enable_watchdog=False)
        return engine

    def test_agent_initialization(self, config_engine):
        agent = RegimeAgent(config_engine)
        assert agent.agent_id == "regime_agent"
        assert agent._llm_manager is None  # LLM disabled

    def test_feature_extraction(self, config_engine):
        agent = RegimeAgent(config_engine)
        # Create sample OHLCV data
        dates = pd.date_range("2025-01-01", periods=100, freq="D")
        df = pd.DataFrame({
            "open": np.random.rand(100) * 100 + 100,
            "high": np.random.rand(100) * 100 + 105,
            "low": np.random.rand(100) * 100 + 95,
            "close": np.random.rand(100) * 100 + 100,
            "volume": np.random.randint(100000, 1000000, 100),
        }, index=dates)
        df["sma_50"] = df["close"].rolling(50).mean()
        df["sma_200"] = df["close"].rolling(200).mean()
        indicators = {
            "rsi": 45.0,
            "macd": 1.5,
            "macd_hist": 0.5,
            "atr": 2.0,
        }
        features = agent._extract_features(df, indicators)
        assert "close" in features
        assert "trend_up" in features
        assert "atr_ratio" in features

    def test_rule_based_classification(self, config_engine):
        agent = RegimeAgent(config_engine)
        features = {
            "close": 150.0,
            "sma_50": 145.0,
            "sma_200": 140.0,
            "price_vs_sma200_pct": 7.14,
            "trend_up": True,
            "trend_down": False,
            "rsi": 55,
            "atr": 3.0,
            "atr_ratio": 1.0,
        }
        regime = agent._classify_with_rules(features)
        assert regime.regime == "trending_bullish"
        assert regime.confidence > 0.7

    def test_high_volatility_detection(self, config_engine):
        agent = RegimeAgent(config_engine)
        features = {
            "close": 100.0,
            "sma_50": 100.0,
            "sma_200": 100.0,
            "price_vs_sma200_pct": 0,
            "trend_up": False,
            "trend_down": False,
            "rsi": 50,
            "atr": 10.0,
            "atr_ratio": 3.0,  # 3x normal = high vol
        }
        regime = agent._classify_with_rules(features)
        assert regime.regime == "high_volatility"

    def test_range_bound_detection(self, config_engine):
        agent = RegimeAgent(config_engine)
        features = {
            "close": 100.0,
            "sma_50": 100.5,
            "sma_200": 100.0,
            "price_vs_sma200_pct": 0,
            "trend_up": False,
            "trend_down": False,
            "rsi": 50,
            "atr": 0.3,
            "atr_ratio": 0.3,  # low vol
        }
        regime = agent._classify_with_rules(features)
        assert regime.regime in ("range_bound", "low_volatility")  # low vol can be either


class TestRegimeAgentIntegration:
    """Integration tests (require LLM disabled)"""

    @pytest.fixture
    def config_engine(self, tmp_path):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "config.yaml"
        config_file.write_text("llm:\n  enabled: false\n")
        return YAMLConfigEngine(config_dir=str(config_dir), enable_watchdog=False)

    async def test_run_with_data(self, config_engine):
        agent = RegimeAgent(config_engine)
        # Create sample data
        dates = pd.date_range("2025-01-01", periods=30, freq="D")
        df = pd.DataFrame({
            "close": np.linspace(100, 110, 30),
            "high": np.linspace(102, 112, 30),
            "low": np.linspace(98, 108, 30),
            "volume": np.random.randint(100000, 1000000, 30),
        }, index=dates)
        indicators = {
            "sma_50": 105.0,
            "sma_200": 102.0,
            "rsi": 60,
            "macd": 0.5,
            "macd_hist": 0.1,
            "atr": 1.5,
        }

        from finance_service.agents.agent_interface import AgentReport
        result = await agent.run({
            "symbol": "AAPL",
            "ohlcv_data": df,
            "indicators": indicators,
        })

        assert isinstance(result, AgentReport)
        assert result.status == "success"
        assert result.payload["regime"]["regime"] in (
            "trending_bullish", "trending_bearish", "range_bound", "high_volatility", "low_volatility"
        )
