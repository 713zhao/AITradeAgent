"""NewsAgent - Fetches financial news and analyzes sentiment (with optional LLM).

Features:
- Fetches news from multiple sources (yfinance, OpenBB)
- LLM-powered sentiment with narrative extraction (if LLM enabled)
- Falls back to VADER sentiment when LLM disabled
- Caches results (1h for news, 24h for LLM analysis)
"""
import json
import logging
import re
import sqlite3
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from pathlib import Path
import numpy as np

from finance_service.agents.agent_interface import Agent, AgentReport
from finance_service.core.event_bus import Event, Events, get_event_bus
from finance_service.core.yaml_config import YAMLConfigEngine

logger = logging.getLogger(__name__)


class _NewsCache:
    """Simple SQLite cache for news analysis results.

    Not thread-safe; intended for single-process use.
    """
    def __init__(self, db_path: str, ttl_minutes: int = 60):
        self.db_path = Path(db_path)
        self.ttl = timedelta(minutes=ttl_minutes)
        self._init_db()

    def _init_db(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS news_cache (
                    symbol TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    cached_at TEXT NOT NULL
                )
            """)
            conn.commit()

    def get(self, symbol: str) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "SELECT data, cached_at FROM news_cache WHERE symbol = ?",
                (symbol,)
            )
            row = cur.fetchone()
            if not row:
                return None
            data_json, cached_at_str = row
            cached_at = datetime.fromisoformat(cached_at_str)
            if datetime.utcnow() - cached_at > self.ttl:
                return None
            return json.loads(data_json)

    def set(self, symbol: str, payload: Dict[str, Any]):
        cached_at = datetime.utcnow().isoformat()
        data_json = json.dumps(payload)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO news_cache (symbol, data, cached_at) VALUES (?, ?, ?)",
                (symbol, data_json, cached_at)
            )
            conn.commit()


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
        self._llm_manager = None
        self._vader = None
        try:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
            self._vader = SentimentIntensityAnalyzer()
        except ImportError:
            pass
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

    async def run(self, symbol: str, **kwargs) -> Optional[AgentReport]:
        """Run news analysis for a given symbol.
        
        Args:
            symbol: Stock ticker symbol
            **kwargs: Additional arguments (ignored, for compatibility)
        """
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

    # ─── LEGACY FETCH METHODS (stubs) ───────────────────────────────────────────
    # These are kept for backward compatibility with old tests. They now delegate
    # to the unified _fetch_news which uses yfinance.

    async def _fetch_alphavantage(self, symbol: str) -> List[Dict]:
        """Legacy Alpha Vantage fetcher - returns empty list (not supported anymore)."""
        logger.debug(f"_fetch_alphavantage called for {symbol} but returning [] (unsupported)")
        return []

    async def _fetch_finnhub(self, symbol: str) -> List[Dict]:
        """Legacy Finnhub fetcher - returns empty list (not supported anymore)."""
        logger.debug(f"_fetch_finnhub called for {symbol} but returning [] (unsupported)")
        return []

    async def _fetch_yahoo(self, symbol: str) -> List[Dict]:
        """Legacy Yahoo fetcher - delegates to _fetch_news."""
        return self._fetch_news(symbol)

    # ─── BACKWARD COMPATIBILITY FOR OLD TEST INTERFACE ─────────────────────────

    # ─── BACKWARD COMPATIBILITY ────────────────────────────────────────────────
    # These methods implement the old API that tests expect. New code should use
    # the NewsAnalysis dataclass and the new _analyze_with_vader/_analyze_with_llm.

    def _analyze_sentiment(self, articles: List[Dict]) -> tuple[float, str]:
        """Analyze sentiment for a list of articles (old test interface).

        Expects articles with keys: 'headline', 'summary', 'av_sentiment_score' (optional)
        Returns: (score: float between -1 and 1, label: str)
        """
        if not articles:
            return 0.0, "neutral"
        scores = []
        for art in articles:
            # Start with Alpha Vantage score if provided
            av_score = art.get('av_sentiment_score')
            if av_score is not None:
                try:
                    scores.append(float(av_score))
                    continue
                except (ValueError, TypeError):
                    pass
            # Fallback to VADER
            if self._vader:
                text = art.get('headline', '') + ". " + art.get('summary', '')
                vader_score = self._vader.polarity_scores(text)['compound']
                scores.append(vader_score)
            else:
                scores.append(0.0)
        overall = sum(scores) / len(scores) if scores else 0.0
        overall = max(-1.0, min(1.0, overall))  # clamp
        # Determine label
        if overall >= 0.3:
            label = "bullish"
        elif overall <= -0.3:
            label = "bearish"
        else:
            label = "neutral"
        return overall, label

    def _analyze_sentiment(self, articles: List[Dict]) -> tuple[float, str]:
        """Analyze sentiment for a list of articles (old test interface).

        Expects articles with keys: 'headline', 'summary', 'av_sentiment_score' (optional)
        Returns: (score: float between -1 and 1, label: str)
        """
        if not articles:
            return 0.0, "neutral"
        scores = []
        for art in articles:
            # Alpha Vantage score and VADER fallback
            av_score = art.get('av_sentiment_score')
            if av_score is not None:
                try:
                    av = float(av_score)
                except (ValueError, TypeError):
                    av = None
            else:
                av = None

            vader_score = None
            if self._vader:
                text = art.get('headline', '') + ". " + art.get('summary', '')
                vader_score = self._vader.polarity_scores(text)['compound']

            # Blend: if both available, average them; otherwise use whichever exists
            if av is not None and vader_score is not None:
                blended = (av + vader_score) / 2
            elif av is not None:
                blended = av
            elif vader_score is not None:
                blended = vader_score
            else:
                blended = 0.0
            scores.append(blended)

        overall = sum(scores) / len(scores) if scores else 0.0
        overall = max(-1.0, min(1.0, overall))  # clamp

        # Determine label (tests expect 0.3/-0.3 thresholds)
        if overall >= 0.3:
            label = "bullish"
        elif overall <= -0.3:
            label = "bearish"
        else:
            label = "neutral"
        return overall, label

    def _identify_catalysts(self, articles: List[Dict], sentiment_score: float) -> List[str]:
        """Extract catalyst events from article headlines and summaries (old test interface)."""
        catalysts = []
        # Keyword patterns for catalysts
        pattern_map = [
            (r'beats?\s+earnings', 'earnings beat'),
            (r'beat\s+estimates|estimates\s+beaten', 'earnings beat'),
            (r'missed?\s+earnings', 'earnings miss'),
            (r'upgrade', 'analyst upgrade'),
            (r'downgrade', 'analyst downgrade'),
            (r'acquisition|buyout|merger', 'merger/acquisition'),
            (r'new\s+product|unveiled|launch', 'product launch'),
            (r'FDA.*approv|regulatory\s+approval|approved', 'regulatory approval'),
            (r'guidance\s+raised|raised\s+guidance', 'guidance raised'),
            (r'guidance\s+lowered|cut\s+guidance', 'guidance lowered'),
            (r'insider\s+buy|executive\s+ purchase', 'insider buying'),
            (r'short\s+squeeze', 'short squeeze'),
        ]
        for art in articles:
            text = (art.get('headline', '') + ' ' + art.get('summary', '')).lower()
            for regex, catalyst in pattern_map:
                if re.search(regex, text, re.IGNORECASE):
                    catalysts.append(catalyst)
        # Fallback based on strong sentiment when no keywords match
        if not catalysts:
            if sentiment_score >= 0.5:
                catalysts.append('strong positive sentiment')
            elif 0.3 <= sentiment_score < 0.5:
                catalysts.append('positive news flow')
            elif sentiment_score <= -0.5:
                catalysts.append('strong negative sentiment')
            elif -0.5 < sentiment_score <= -0.3:
                catalysts.append('negative news flow')

        # Remove duplicates while preserving order
        seen = set()
        unique = []
        for c in catalysts:
            if c not in seen:
                seen.add(c)
                unique.append(c)
        return unique
