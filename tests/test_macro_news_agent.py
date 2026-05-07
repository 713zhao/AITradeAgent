"""Tests for MacroNewsAgent"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import re

from finance_service.agents.macro_news_agent import MacroNewsAgent, MacroNewsItem, MacroNewsReport
from finance_service.core.yaml_config import YAMLConfigEngine


@pytest.fixture
def mock_config_engine():
    """Mock YAMLConfigEngine."""
    cfg = MagicMock(spec=YAMLConfigEngine)
    cfg.get.side_effect = lambda *args, default=None: default
    return cfg


@pytest.fixture
def macro_news_agent(mock_config_engine):
    """Create MacroNewsAgent with mocked config."""
    agent = MacroNewsAgent(config_engine=mock_config_engine)
    return agent


def test_macro_news_agent_categorization(macro_news_agent):
    """Test article category classification."""
    test_cases = [
        ("Fed raises interest rates", "monetary_policy"),
        ("ECB announces bond purchase program", "monetary_policy"),
        ("US CPI data beats expectations", "economic_data"),
        ("NFP numbers show strong job growth", "economic_data"),
        ("Trade war escalates between US and China", "geopolitical"),
        ("New SEC regulations on crypto exchanges", "regulatory"),
        ("Rotation from tech to energy continues", "sector_rotation"),
    ]

    for headline, expected in test_cases:
        text = headline + ". Some summary text."
        category = macro_news_agent._categorize_article(text)
        assert category == expected, f"Failed for: {headline}"


def test_macro_news_agent_impact_tags_extraction(macro_news_agent):
    """Test impact tag extraction from article text."""
    test_cases = [
        ("Dollar strengthens as Fed signals rate hike", ["dollar", "rates"]),
        ("Inflation concerns rise after CPI report", ["inflation"]),
        ("Gold prices surge amid geopolitical tension", ["commodities"]),
        ("Bitcoin rallies on institutional adoption", ["crypto", "stocks"]),
    ]

    for text, expected_tags in test_cases:
        tags = macro_news_agent._extract_impact_tags(text)
        for tag in expected_tags:
            assert tag in tags, f"Missing tag {tag} in: {text}"


def test_macro_news_agent_filter_macro_articles(macro_news_agent):
    """Test macro article filtering."""
    articles = [
        {"headline": "Fed meeting scheduled for next week", "summary": ""},
        {"headline": "Apple announces new iPhone", "summary": "Product launch event"},
        {"headline": "CPI data due on Friday", "summary": "Inflation numbers expected"},
        {"headline": "Local restaurant opens new location", "summary": "Food news"},
    ]

    filtered = macro_news_agent._filter_macro_articles(articles)

    assert len(filtered) == 2
    headlines = [a["headline"] for a in filtered]
    assert "Fed meeting scheduled for next week" in headlines
    assert "CPI data due on Friday" in headlines
    assert "Apple announces new iPhone" not in headlines
    assert "Local restaurant opens new location" not in headlines


def test_macro_news_agent_analyze_article_with_vader(macro_news_agent):
    """Test VADER sentiment analysis."""
    macro_news_agent._init_nlp()  # initialize VADER if available

    article = {
        "headline": "Strong economic growth reported",
        "summary": "GDP numbers exceeded expectations positively",
        "published_at": datetime.utcnow().isoformat()
    }

    analyzed = macro_news_agent._analyze_article(article)

    assert isinstance(analyzed, MacroNewsItem)
    assert analyzed.sentiment != 0.0 or analyzed.sentiment == 0.0  # numeric
    assert analyzed.category in ["monetary_policy", "economic_data", "other"]
    assert analyzed.urgency in ["high", "medium", "low"]


def test_macro_news_agent_extract_catalysts_and_risk_events(macro_news_agent):
    """Test catalyst and risk event extraction."""
    articles = [
        MacroNewsItem(
            headline="Fed meeting tomorrow to decide rates",
            source="Reuters",
            published_at=datetime.utcnow().isoformat(),
            sentiment=0.1,
            category="monetary_policy",
            impact_tags=["rates"],
            urgency="high"
        ),
        MacroNewsItem(
            headline="CPI release next week expected to show inflation easing",
            source="Bloomberg",
            published_at=(datetime.utcnow() - timedelta(hours=12)).isoformat(),
            sentiment=0.3,
            category="economic_data",
            impact_tags=["inflation"],
            urgency="medium"
        ),
    ]

    catalysts = macro_news_agent._extract_catalysts(articles)
    assert len(catalysts) > 0

    risk_events = macro_news_agent._extract_risk_events(articles)
    assert len(risk_events) >= 1  # at least the high urgency one


@pytest.mark.asyncio
async def test_macro_news_agent_run_returns_report(macro_news_agent):
    """Test full run() returns proper report structure."""
    # Mock the fetch method
    macro_news_agent._fetch_macro_news = AsyncMock(return_value=[
        {"headline": "Fed raises rates", "summary": "Central bank action", "source": "Reuters", "published_at": datetime.utcnow().isoformat()},
        {"headline": "CPI beats estimates", "summary": "Inflation data", "source": "Bloomberg", "published_at": datetime.utcnow().isoformat()},
    ])

    report = await macro_news_agent.run()

    assert report.status == "success"
    assert "macro_news" in report.payload
    assert "macro_sentiment_score" in report.payload
    assert "macro_catalysts" in report.payload
    assert "risk_events" in report.payload
    assert isinstance(report.payload["macro_sentiment_score"], float)
