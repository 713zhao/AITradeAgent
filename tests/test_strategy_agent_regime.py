"""Tests for StrategyAgent regime integration."""
import pytest
from unittest.mock import MagicMock, patch
from finance_service.agents.strategy_agent import StrategyAgent
from finance_service.core.yaml_config import YAMLConfigEngine
import pandas as pd
import numpy as np


class TestStrategyAgentRegimeIntegration:
    """Test StrategyAgent confidence adjustment based on regime"""

    @pytest.fixture
    def config_engine(self, tmp_path):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "config.yaml"
        config_file.write_text("""
finance:
  strategy:
    position_cooling_hours: 24
        """)
        engine = YAMLConfigEngine(config_dir=str(config_dir), enable_watchdog=False)
        return engine

    def test_adjust_confidence_default(self, config_engine):
        agent = StrategyAgent(config_engine)
        # Without regime, confidence unchanged
        conf = agent._adjust_confidence(0.75)
        assert conf == 0.75

    def test_adjust_confidence_trending_bullish(self, config_engine):
        agent = StrategyAgent(config_engine)
        agent._current_regime = {
            "regime": "trending_bullish",
            "confidence": 0.9,
        }
        conf = agent._adjust_confidence(0.70)
        # Expect boost: +5% + (0.9*5%) = +9.5% -> 0.80
        assert 0.79 <= conf <= 0.81

    def test_adjust_confidence_high_volatility(self, config_engine):
        agent = StrategyAgent(config_engine)
        agent._current_regime = {
            "regime": "high_volatility",
            "confidence": 0.0,  # Not used
        }
        conf = agent._adjust_confidence(0.80)
        assert conf == 0.70  # -10% penalty

    def test_adjust_confidence_low_volatility_high_conf(self, config_engine):
        agent = StrategyAgent(config_engine)
        agent._current_regime = {
            "regime": "low_volatility",
            "confidence": 0.0,
        }
        conf = agent._adjust_confidence(0.80)
        assert conf == 0.85  # +5% boost

    def test_adjust_confidence_low_volatility_low_conf(self, config_engine):
        agent = StrategyAgent(config_engine)
        agent._current_regime = {
            "regime": "low_volatility",
            "confidence": 0.0,
        }
        conf = agent._adjust_confidence(0.40)
        assert conf == 0.40  # low signals ignored, no boost


class TestStrategyAgentRuleLoading:
    """Test rule loading from YAML config"""

    @pytest.fixture
    def config_engine(self, tmp_path):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "config.yaml"
        config_file.write_text("""
finance:
  strategy:
    type: "baseline_rule"
        """)
        return YAMLConfigEngine(config_dir=str(config_dir), enable_watchdog=False)

    def test_load_rules_from_file(self, config_engine, tmp_path):
        # Create rules.yaml
        rules_path = tmp_path / "rules.yaml"
        rules_path.write_text("""
rules:
  - name: "test_entry"
    type: entry
    indicator: rsi
    condition: less_than
    value: 30
  - name: "test_exit"
    type: exit
    indicator: rsi
    condition: greater_than
    value: 70
""")
        # Patch the config engine to return our rules file path
        config_engine._config = {
            "finance": {
                "strategy": {
                    "rule_file": str(rules_path)
                }
            }
        }
        agent = StrategyAgent(config_engine)
        assert len(agent.rule_strategy.rules) == 2
        assert len(agent.rule_strategy.entry_rules) == 1
        assert len(agent.rule_strategy.exit_rules) == 1
