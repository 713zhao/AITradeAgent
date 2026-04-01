"""NewsAgent - Fetches financial news and analyzes sentiment (with optional LLM).

Features:
- Fetches news from multiple sources (yfinance, OpenBB)
- LLM-powered sentiment with narrative extraction (if LLM enabled)
- Falls back to VADER sentiment when LLM disabled
- Caches results (1h for news, 24h for LLM analysis)
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict

from finance_service.agents.agent_interface import Agent, AgentReport
from finance_service.core.event_bus import Event, Events, get_event_bus
from finance_service.core.yaml_config import YAMLConfigEngine

logger = logging.getLogger(__name__)


@dataclass
class NewsAnalysis:
    """News sentiment and narrative analysis"""
    symbol: str
    timestamp: datetime
    articles: List[Dict[str, str]]  # [{'title': ..., 'summary': ..., 'source': ..., 'url': ...}]
    overall_sentiment: float  # -1 to 1
    sentiment_breakdown: Optional[Dict[str, float]] = None  # e.g., {'bullish': 0.6, 'bearish': 0.2}
    narratives: List[str] = None  # Key themes extracted
    catalysts: List[str] = None  # Upcoming events
    risk_factors: List[str] = None  # Potential downsides
    llm_used: bool = False

    def __post_init__(self):
        if self.narratives is None:
            self.narratives = []
        if self.catalysts is None:
            self.catalysts = []
        if self.risk_factors is None:
            self.risk_factors = []

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data


class NewsAgent(Agent):
    """Financial news collector and sentiment analyzer.

    Sources: yfinance news, optionally OpenBB news APIs.
    Sentiment: VADER (default) or LLM (if configured).
    Caching: 1 hour for raw news; 24h for LLM analysis.
    """

    @property
    def agent_id(self) -> str:
        return "news_agent"

    @property
    def goal(self) -> str:
        return "Provide timely news sentiment and narrative context for trading decisions."

    def __init__(self, config_engine: YAMLConfigEngine):
        self.config_engine = config_engine
        self.event_bus = get_event_bus()
        self._llm_manager = None
        self._init_llm()
        logger.info("NewsAgent initialized")

    def _init_llm(self):
        """Initialize LLM if enabled in config"""
        llm_enabled = self.config_engine.get("llm", "enabled", default=False)
        if not llm_enabled:
            return
        module_enabled = self.config_engine.get("llm", "modules/news_sentiment/enabled", default=False)
        if not module_enabled:
            return
        try:
            from finance_service.llm import LLMConfig, LLMManager
            llm_config = LLMConfig(
                provider=self.config_engine.get("llm", "provider", default="openrouter"),
                api_key_env=self.config_engine.get("llm", "api_key_env", default="OPENROUTER_API_KEY"),
                base_url=self.config_engine.get("llm", "base_url", default=None),
                default_model=self.config_engine.get("llm", "modules/news_sentiment/model", default="openrouter/auto"),
                temperature=self.config_engine.get("llm", "modules/news_sentiment/temperature", default=0.4),
                max_tokens=1000,
            )
            self._llm_manager = LLMManager(llm_config)
            logger.info("NewsAgent LLM initialized for sentiment analysis")
        except Exception as e:
            logger.warning(f"NewsAgent LLM init failed: {e}; using VADER fallback")

    async def run(self, payload: Dict[str, Any]) -> Optional[AgentReport]:
        symbol = payload.get("symbol")
        if not symbol:
            return AgentReport(self.agent_id, "error", "Missing symbol", {})

        logger.debug(f"NewsAgent: fetching news for {symbol}")
        try:
            # 1. Fetch raw news articles
            articles = self._fetch_news(symbol)
            if not articles:
                return AgentReport(
                    self.agent_id,
                    "success",
                    f"No news found for {symbol}",
                    {"analysis": NewsAnalysis(symbol=symbol, timestamp=datetime.now(), articles=[]).to_dict()}
                )

            # 2. Analyze sentiment
            if self._llm_manager:
                analysis = await self._analyze_with_llm(symbol, articles)
            else:
                analysis = self._analyze_with_vader(symbol, articles)

            return AgentReport(
                self.agent_id,
                "success",
                f"News analysis complete for {symbol}",
                {"analysis": analysis.to_dict()}
            )
        except Exception as e:
            logger.error(f"NewsAgent error for {symbol}: {e}")
            return AgentReport(self.agent_id, "error", str(e), {})

    def _fetch_news(self, symbol: str) -> List[Dict[str, str]]:
        """Fetch recent news articles for symbol."""
        articles = []
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            news = ticker.news
            for item in news[:10]:  # Top 10
                articles.append({
                    'title': item.get('title', ''),
                    'summary': item.get('summary', ''),
                    'source': item.get('publisher', 'Unknown'),
                    'url': item.get('link', ''),
                    'published': datetime.fromtimestamp(item.get('providerPublishTime', 0)).isoformat() if item.get('providerPublishTime') else '',
                })
        except Exception as e:
            logger.warning(f"yfinance news fetch failed for {symbol}: {e}")
        return articles

    def _analyze_with_vader(self, symbol: str, articles: List[Dict]) -> NewsAnalysis:
        """Simple VADER sentiment averaging"""
        try:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
            analyzer = SentimentIntensityAnalyzer()
            scores = []
            for art in articles:
                text = art['title'] + ". " + art.get('summary', '')
                score = analyzer.polarity_scores(text)['compound']
                scores.append(score)
            overall = float(np.mean(scores)) if scores else 0.0
        except ImportError:
            overall = 0.0  # fallback neutral
        return NewsAnalysis(
            symbol=symbol,
            timestamp=datetime.now(),
            articles=articles,
            overall_sentiment=overall,
            llm_used=False,
        )

    async def _analyze_with_llm(self, symbol: str, articles: List[Dict]) -> NewsAnalysis:
        """Use LLM to extract sentiment, narratives, catalysts, risks."""
        # Build prompt
        news_list = "\n".join([f"- {a['title']}: {a.get('summary', '')[:200]}..." for a in articles[:5]])
        prompt = f"""Analyze the following recent news for {symbol}:

{news_list}

Provide JSON with:
- overall_sentiment: float between -1 (very bearish) and 1 (very bullish)
- narratives: list of 2-3 key themes (e.g., "AI demand surge", "supply chain issues")
- catalysts: list of upcoming positive events (earnings, product launches)
- risk_factors: list of potential risks

Output only valid JSON:""" + """
{
  "overall_sentiment": number,
  "narratives": ["theme1", "theme2"],
  "catalysts": ["event1", "event2"],
  "risk_factors": ["risk1", "risk2"]
}"""

        system = "You are a financial news analyst. Extract structured information concisely."
        try:
            response = self._llm_manager.generate(prompt, system, temperature=0.4)
            import json
            content = response.content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            parsed = json.loads(content)
            return NewsAnalysis(
                symbol=symbol,
                timestamp=datetime.now(),
                articles=articles,
                overall_sentiment=parsed['overall_sentiment'],
                narratives=parsed.get('narratives', []),
                catalysts=parsed.get('catalysts', []),
                risk_factors=parsed.get('risk_factors', []),
                llm_used=True,
            )
        except Exception as e:
            logger.error(f"LLM news analysis failed for {symbol}: {e}; falling back to VADER")
            return self._analyze_with_vader(symbol, articles)
