"""Tests for MarketRegimeAgent"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import pandas as pd
import numpy as np

from finance_service.agents.market_regime_agent import MarketRegimeAgent, MarketRegime, IndexMetrics, MarketBreadth
from finance_service.core.yaml_config import YAMLConfigEngine


@pytest.fixture
def mock_config_engine():
    """Mock YAMLConfigEngine with required methods."""
    cfg = MagicMock(spec=YAMLConfigEngine)
    cfg.get.side_effect = lambda *args, default=None: default
    return cfg


@pytest.fixture
def mock_data_agent():
    """Mock DataAgent with _fetch_data_for_symbol method."""
    da = MagicMock()
    da._fetch_data_for_symbol = AsyncMock()
    return da


@pytest.fixture
def market_regime_agent(mock_config_engine, mock_data_agent):
    """Create MarketRegimeAgent with mocked dependencies."""
    agent = MarketRegimeAgent(
        config_engine=mock_config_engine,
        data_agent=mock_data_agent,
        market_scanner=None
    )
    return agent


def create_mock_index_df(days: int = 90, start_price: float = 100.0) -> pd.DataFrame:
    """Create a mock OHLCV DataFrame for index testing."""
    dates = pd.date_range(end=datetime.now().date(), periods=days, freq='D')
    prices = start_price * (1 + 0.001 * np.random.randn(days))  # small random walk
    df = pd.DataFrame({
        'open': prices * (1 - 0.005),
        'high': prices * (1 + 0.01),
        'low': prices * (1 - 0.01),
        'close': prices,
        'volume': np.random.randint(1_000_000, 5_000_000, size=days)
    }, index=dates)
    return df


@pytest.mark.asyncio
async def test_market_regime_agent_compute_regime_all_indices(market_regime_agent, mock_data_agent):
    """Test MarketRegimeAgent computes correctly with all indices available."""
    # Setup mock data for each index
    df = create_mock_index_df()
    mock_data_agent._fetch_data_for_symbol.return_value = df

    report = await market_regime_agent.run()

    assert report.status == "success"
    payload = report.payload
    assert "regime" in payload
    assert "indices" in payload

    # Check regime flags exist
    regime = payload["regime"]
    assert "risk_on" in regime
    assert "volatility_regime" in regime
    assert "trend_strength" in regime
    assert "summary" in regime

    # Check indices present
    indices = payload["indices"]
    for key in ["SP500", "NASDAQ", "DOW", "VIX", "RUSSELL2000"]:
        assert key in indices
        idx = indices[key]
        assert "price" in idx
        assert "change_pct_1d" in idx
        assert "vs_sma200_pct" in idx


@pytest.mark.asyncio
async def test_market_regime_agent_handles_missing_index(market_regime_agent, mock_data_agent):
    """Test agent handles index fetch failure gracefully."""
    # Return None for one index
    def side_effect(symbol, start, end, interval):
        if symbol == "^VIX":
            return None
        return create_mock_index_df()

    mock_data_agent._fetch_data_for_symbol.side_effect = side_effect

    report = await market_regime_agent.run()

    assert report.status == "success"
    # Should still have other indices
    indices = report.payload["indices"]
    assert "SP500" in indices
    assert "VIX" not in indices  # missing, not present


def test_market_regime_agent_derive_regime_with_vix_high(market_regime_agent):
    """Test regime derivation with high VIX indicates risk-off."""
    indices = {
        "SP500": IndexMetrics(
            symbol="^GSPC", name="S&P 500", price=4200, change_pct_1d=0.5,
            change_pct_5d=1.0, vs_sma20_pct=2.0, vs_sma50_pct=3.0, vs_sma200_pct=4.0,
            ytd_return=10.0, volume_ratio_vs_20d=1.1
        ),
        "VIX": IndexMetrics(
            symbol="^VIX", name="VIX", price=35.0, change_pct_1d=5.0,
            change_pct_5d=0.0, vs_sma20_pct=10.0, vs_sma50_pct=15.0, vs_sma200_pct=20.0,
            ytd_return=-5.0, volume_ratio_vs_20d=1.2
        ),
        "NASDAQ": IndexMetrics(
            symbol="^IXIC", name="NASDAQ", price=14000, change_pct_1d=0.8,
            change_pct_5d=1.5, vs_sma20_pct=3.0, vs_sma50_pct=5.0, vs_sma200_pct=6.0,
            ytd_return=15.0, volume_ratio_vs_20d=1.1
        )
    }
    breadth = MarketBreadth(
        advancers_ratio=0.6, new_highs_20d=50, new_lows_20d=10,
        volume_ratio_vs_avg=1.0, symbols_above_sma20_pct=0.6, symbols_above_sma50_pct=0.55
    )

    regime = market_regime_agent._derive_regime(indices, breadth)

    assert regime.volatility_regime == "high"
    assert regime.risk_on is False  # high VIX -> risk-off


def test_market_regime_agent_derive_regime_with_weak_breadth(market_regime_agent):
    """Test regime derivation with weak breadth indicates risk-off."""
    indices = {
        "SP500": IndexMetrics(
            symbol="^GSPC", name="S&P 500", price=4000, change_pct_1d=-0.2,
            change_pct_5d=-1.0, vs_sma20_pct=-1.0, vs_sma50_pct=-2.0, vs_sma200_pct=-3.0,
            ytd_return=-5.0, volume_ratio_vs_20d=0.9
        ),
        "VIX": IndexMetrics(
            symbol="^VIX", name="VIX", price=22.0, change_pct_1d=1.0,
            change_pct_5d=0.5, vs_sma20_pct=5.0, vs_sma50_pct=8.0, vs_sma200_pct=10.0,
            ytd_return=15.0, volume_ratio_vs_20d=1.0
        )
    }
    breadth = MarketBreadth(
        advancers_ratio=0.40, new_highs_20d=10, new_lows_20d=80,
        volume_ratio_vs_avg=1.0, symbols_above_sma20_pct=0.45, symbols_above_sma50_pct=0.40
    )

    regime = market_regime_agent._derive_regime(indices, breadth)

    assert regime.trend_strength in ["weak", "moderate"]
    assert regime.risk_on is False  # weak breadth -> risk-off


def test_market_regime_agent_cache_returns_cached(market_regime_agent):
    """Test that cached result is returned when not expired."""
    import asyncio
    # Set a valid cache
    market_regime_agent._cache = {"test": "data"}
    market_regime_agent._cache_expiry = datetime.utcnow() + timedelta(hours=1)

    report = asyncio.run(market_regime_agent.run())

    assert report.status == "success"
    assert report.payload == {"test": "data"}


def test_market_regime_agent_cache_expired(market_regime_agent, mock_data_agent):
    """Test that expired cache triggers recompute."""
    import asyncio
    df = create_mock_index_df()
    mock_data_agent._fetch_data_for_symbol.return_value = df

    # Set expired cache
    market_regime_agent._cache = {"old": "data"}
    market_regime_agent._cache_expiry = datetime.utcnow() - timedelta(hours=1)

    report = asyncio.run(market_regime_agent.run())

    assert report.status == "success"
    assert report.payload != {"old": "data"}
