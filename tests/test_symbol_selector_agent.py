"""Tests for SymbolSelectorAgent"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import pandas as pd
import numpy as np

from finance_service.agents.symbol_selector_agent import SymbolSelectorAgent, CandidateData
from finance_service.core.yaml_config import YAMLConfigEngine


@pytest.fixture
def mock_config_engine():
    """Mock YAMLConfigEngine with sensible defaults."""
    cfg = MagicMock(spec=YAMLConfigEngine)
    def get_side_effect(*args, default=None):
        # Return default for most keys
        path = "/".join(str(a) for a in args)
        if "symbol_selector/enabled" in path:
            return True
        if "symbol_selector/max_input_symbols" in path:
            return 50
        if "symbol_selector/cache_ttl_hours" in path:
            return 24
        if "finance/symbol_selector/model" in path:
            return "openrouter/auto"
        if "finance/symbol_selector/temperature" in path:
            return 0.2
        if "market_regime_agent/cache_ttl_minutes" in path:
            return 60
        if "macro_news/cache_ttl_minutes" in path:
            return 360
        if "macro_news/lookback_hours" in path:
            return 48
        if "macro_news/max_articles" in path:
            return 20
        return default
    cfg.get.side_effect = get_side_effect
    return cfg


@pytest.fixture
def mock_dependencies(mock_config_engine):
    """Create all mocked dependencies for SymbolSelectorAgent."""
    data_agent = MagicMock()
    market_scanner = MagicMock()
    market_scanner.get_watchlist_symbols.return_value = []
    market_regime = MagicMock()
    macro_news = MagicMock()
    analysis_agent = MagicMock()
    news_agent = MagicMock()

    # Mock run methods to return AgentReport-like objects
    market_regime.run = AsyncMock(return_value=MagicMock(
        status="success",
        payload={
            "regime": {"risk_on": True, "volatility_regime": "normal", "trend_strength": "moderate", "summary": "Test regime"},
            "indices": {"SP500": {"price": 4200, "change_pct_1d": 0.5, "vs_sma200_pct": 3.0, "ytd_return": 10.0}},
            "breadth": {"advancers_ratio": 0.65, "symbols_above_sma50_pct": 0.60}
        }
    ))
    macro_news.run = AsyncMock(return_value=MagicMock(
        status="success",
        payload={
            "macro_sentiment_score": 0.2,
            "macro_catalysts": ["Fed meeting"],
            "risk_events": []
        }
    ))
    news_agent.run = AsyncMock(return_value=MagicMock(
        status="success",
        payload={
            "sentiment_score": 0.5,
            "sentiment_label": "bullish",
            "catalysts": ["earnings beat"],
            "news_count": 3
        }
    ))

    return {
        "data_agent": data_agent,
        "market_scanner": market_scanner,
        "market_regime_agent": market_regime,
        "macro_news_agent": macro_news,
        "analysis_agent": analysis_agent,
        "news_agent": news_agent
    }


def create_mock_ohlcv_df(days: int = 60, start_price: float = 100.0) -> pd.DataFrame:
    """Create mock OHLCV DataFrame."""
    np.random.seed(42)
    returns = np.random.normal(0.0005, 0.02, days)
    prices = start_price * np.exp(np.cumsum(returns))
    dates = pd.date_range(end=datetime.now().date(), periods=days, freq='D')
    df = pd.DataFrame({
        'open': prices * (1 - 0.005),
        'high': prices * (1 + 0.01),
        'low': prices * (1 - 0.01),
        'close': prices,
        'volume': np.random.randint(1_000_000, 10_000_000, size=days)
    }, index=dates)
    return df


@pytest.fixture
def selector_agent(mock_config_engine, mock_dependencies):
    """Create SymbolSelectorAgent with mocked deps."""
    agent = SymbolSelectorAgent(
        config_engine=mock_config_engine,
        data_agent=mock_dependencies["data_agent"],
        market_scanner=mock_dependencies["market_scanner"],
        market_regime_agent=mock_dependencies["market_regime_agent"],
        macro_news_agent=mock_dependencies["macro_news_agent"],
        analysis_agent=mock_dependencies["analysis_agent"],
        news_agent=mock_dependencies["news_agent"]
    )
    # Stub LLM manager to avoid needing actual API
    agent._llm_manager = MagicMock()
    agent._llm_manager.generate = AsyncMock(return_value='{"rankings": [{"symbol": "AAPL", "total_score": 85, "breakdown": {"technical": 9, "catalyst": 8, "fundamental": 9, "risk_adjusted": 8, "regime_fit": 9}, "rationale": "Strong tech stock in bull market", "position_size_pct": 2.0, "suggested_stop_pct": 8.0}], "summary": "Test ranking"}')
    return agent


def test_symbol_selector_agent_init(selector_agent):
    """Test agent initialization."""
    assert selector_agent.agent_id == "symbol_selector_agent"
    assert selector_agent._llm_manager is not None
    assert selector_agent.cache_ttl_hours == 24


def test_symbol_selector_make_cache_key(selector_agent):
    """Test cache key generation."""
    key1 = selector_agent._make_cache_key(["AAPL", "MSFT", "GOOG"])
    key2 = selector_agent._make_cache_key(["GOOG", "AAPL", "MSFT"])  # same set
    assert key1 == key2
    key3 = selector_agent._make_cache_key(["AAPL", "TSLA"])
    assert key1 != key3


def test_symbol_selector_compute_rsi(selector_agent):
    """Test RSI calculation."""
    prices = pd.Series([100, 102, 101, 105, 107, 106, 108, 110, 109, 111])
    rsi = selector_agent._compute_rsi(prices, period=5)
    assert 0 <= rsi <= 100


def test_symbol_selector_compute_atr(selector_agent):
    """Test ATR calculation."""
    df = pd.DataFrame({
        'high': [105, 106, 107, 108, 109],
        'low': [98, 99, 100, 101, 102],
        'close': [102, 103, 104, 105, 106]
    })
    atr = selector_agent._compute_atr(df, period=3)
    assert atr >= 0


@pytest.mark.asyncio
async def test_symbol_selector_gather_candidate_data(selector_agent, mock_dependencies):
    """Test candidate data gathering."""
    # Mock data_agent._fetch_data_for_symbol to return a DataFrame
    df = create_mock_ohlcv_df()
    mock_dependencies["data_agent"]._fetch_data_for_symbol = AsyncMock(return_value=df)
    mock_dependencies["news_agent"].run = AsyncMock(return_value=MagicMock(
        status="success",
        payload={"sentiment_score": 0.6, "sentiment_label": "bullish", "catalysts": ["product launch"], "news_count": 5}
    ))

    candidate = await selector_agent._fetch_candidate_data("AAPL")

    assert candidate is not None
    assert candidate.symbol == "AAPL"
    assert candidate.theme == "unknown"
    assert "rsi" in candidate.technical_indicators
    assert "current_price" in candidate.price_action
    assert "avg_daily_volume_20d" in candidate.liquidity_metrics


def test_symbol_selector_build_prompt(selector_agent):
    """Test prompt construction."""
    # Create fake candidates
    candidates = [
        CandidateData(
            symbol="AAPL",
            theme="AI",
            technical_indicators={"rsi": 65, "macd": {"value": 1.2, "histogram": 0.3}, "sma_20": 170, "atr": 5},
            price_action={"current_price": 175.50, "price_vs_sma20_pct": 3.0, "ytd_return_pct": 25.0},
            fundamentals=None,
            news_sentiment={"sentiment_score": 0.7, "catalysts": ["AI chip demand"], "article_count": 10},
            liquidity_metrics={"avg_dollar_volume_20d": 30_000_000_000, "liquidity_tier": "high"},
            risk_metrics={"beta_estimate": 1.3, "days_to_earnings": 15}
        )
    ]

    market_context = {
        "regime": {
            "summary": "Risk-on bullish regime with moderate trend",
            "risk_on": True,
            "volatility_regime": "low",
            "trend_strength": "moderate"
        },
        "macro_sentiment_score": 0.3,
        "macro_catalysts": ["Fed meeting next week"],
        "risk_events": []
    }

    prompt = selector_agent._build_prompt(candidates, market_context)

    # Check that key elements are in prompt
    assert "AAPL" in prompt
    assert "Risk-on bullish regime" in prompt
    assert "technical" in prompt.lower()
    assert "$30,000,000,000" in prompt  # formatted dollar volume
    assert "Fed meeting" in prompt


def test_symbol_selector_parse_llm_response_valid(selector_agent):
    """Test parsing of valid LLM JSON response."""
    response = '''
    ```json
    {
      "rankings": [
        {
          "symbol": "NVDA",
          "total_score": 90,
          "breakdown": {"technical": 9, "catalyst": 9, "fundamental": 9, "risk_adjusted": 9, "regime_fit": 9},
          "rationale": "Strong AI leader",
          "position_size_pct": 2.0,
          "suggested_stop_pct": 7.5
        }
      ],
      "summary": "Top stock is NVDA"
    }
    ```
    '''
    rankings = selector_agent._parse_llm_response(response)
    assert len(rankings) == 1
    assert rankings[0]["symbol"] == "NVDA"
    assert rankings[0]["total_score"] == 90
    assert 1.0 <= rankings[0]["position_size_pct"] <= 2.0


def test_symbol_selector_parse_llm_response_invalid(selector_agent):
    """Test parsing with invalid JSON returns empty list."""
    response = "This is not JSON"
    rankings = selector_agent._parse_llm_response(response)
    assert rankings == []


def test_symbol_selector_filter_rejected(selector_agent):
    """Test identification of rejected (unranked) symbols."""
    candidates = [
        CandidateData(symbol="AAPL", theme="Tech", technical_indicators={}, price_action={}, fundamentals=None,
                     news_sentiment={}, liquidity_metrics={}, risk_metrics={}),
        CandidateData(symbol="MSFT", theme="Tech", technical_indicators={}, price_action={}, fundamentals=None,
                     news_sentiment={}, liquidity_metrics={}, risk_metrics={}),
    ]
    rankings = [{"symbol": "AAPL", "total_score": 80, "position_size_pct": 1.5, "suggested_stop_pct": 8.0}]

    rejected = selector_agent._filter_rejected(candidates, rankings)
    assert len(rejected) == 1
    assert rejected[0]["symbol"] == "MSFT"


@pytest.mark.asyncio
async def test_symbol_selector_run_full_pipeline(selector_agent, mock_dependencies):
    """Test full run() method with mocked LLM."""
    # Mock data fetch
    df = create_mock_ohlcv_df()
    mock_dependencies["data_agent"]._fetch_data_for_symbol = AsyncMock(return_value=df)

    payload = {"symbols": ["AAPL", "MSFT"]}
    report = await selector_agent.run(payload)

    assert report.status == "success"
    assert "rankings" in report.payload
    assert "market_context" in report.payload
    assert len(report.payload["rankings"]) > 0
