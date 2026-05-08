"""MacroNewsAgent - Broad market news and macroeconomic catalyst detection.

Monitors general financial news (not symbol-specific) to identify:
- Monetary policy changes (Fed, ECB, etc.)
- Geopolitical events
- Economic data releases (CPI, NFP, GDP)
- Regulatory changes
- Sector rotations
- Market structure shifts

Provides aggregate macro sentiment and risk event tracking for high-level strategy.
"""
import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
import re

from finance_service.agents.agent_interface import Agent, AgentReport
from finance_service.core.event_bus import get_event_bus
from finance_service.core.yaml_config import YAMLConfigEngine
from finance_service.utils.llm_analysis_logger import get_llm_analysis_logger
from finance_service.agents.news_agent import _NewsCache  # reuse cache infrastructure

logger = logging.getLogger(__name__)


@dataclass
class MacroNewsItem:
    """A macroeconomic news article"""
    headline: str
    source: str
    published_at: str
    sentiment: float  # -1 to +1
    category: str  # monetary_policy, geopolitical, economic_data, regulatory, sector_rotation, other
    impact_tags: List[str]
    urgency: str  # high, medium, low


@dataclass
class MacroNewsReport:
    """Aggregate macro news summary"""
    macro_news: List[Dict[str, Any]]
    macro_sentiment_score: float
    macro_catalysts: List[str]
    risk_events: List[str]
    # Per-market breakdowns
    us_macro_news: List[Dict[str, Any]] = field(default_factory=list)
    us_sentiment_score: float = 0.0
    hk_macro_news: List[Dict[str, Any]] = field(default_factory=list)
    hk_sentiment_score: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class MacroNewsAgent(Agent):
    """Agent that fetches and analyzes broad-market macroeconomic news."""

    @property
    def agent_id(self) -> str:
        return "macro_news_agent"

    @property
    def goal(self) -> str:
        return "Provide macroeconomic context and risk event awareness for trading decisions."

    def __init__(self, config_engine: YAMLConfigEngine):
        self.config_engine = config_engine
        self.event_bus = get_event_bus()
        self._cache = _NewsCache(
            db_path=self.config_engine.get("macro_news_agent", "cache_path", default="finance_service/storage/macro_news_cache.sqlite"),
            ttl_minutes=self.config_engine.get("macro_news_agent", "cache_ttl_minutes", default=360)  # 6 hours
        )
        self._init_nlp()

    def _init_nlp(self):
        """Initialize optional LLM or VADER for sentiment"""
        self._vader = None
        try:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
            self._vader = SentimentIntensityAnalyzer()
        except ImportError:
            logger.warning("VADER not available for macro news sentiment")

    async def run(self, payload: Optional[Dict[str, Any]] = None) -> Optional[AgentReport]:
        """
        Fetch and analyze macroeconomic news.

        Args:
            payload: Can include {'force_refresh': bool, 'lookback_hours': int}

        Returns:
            AgentReport with MacroNewsReport payload
        """
        lookback_hours = self.config_engine.get("macro_news_agent", "lookback_hours", default=48)
        max_articles = self.config_engine.get("macro_news_agent", "max_articles", default=20)

        cache_key = f"macro_{lookback_hours}h"
        cached = self._cache.get(cache_key)
        if cached and not (payload and payload.get("force_refresh", False)):
            return AgentReport(
                agent_id=self.agent_id,
                status="success",
                message="Macro news (cached)",
                payload=cached
            )

        try:
            # Fetch from US and HK sources in parallel
            us_articles_raw, hk_articles_raw = await asyncio.gather(
                self._fetch_macro_news(lookback_hours, max_articles, market="US"),
                self._fetch_macro_news(lookback_hours, max_articles, market="HK"),
            )

            # Filter and analyze per market
            us_filtered = self._filter_macro_articles(us_articles_raw, market="US")
            hk_filtered = self._filter_macro_articles(hk_articles_raw, market="HK")

            us_analyzed = [self._analyze_article(a) for a in us_filtered]
            hk_analyzed = [self._analyze_article(a) for a in hk_filtered]

            all_analyzed = us_analyzed + hk_analyzed

            avg_sentiment = sum(a.sentiment for a in all_analyzed) / len(all_analyzed) if all_analyzed else 0.0
            us_sentiment = sum(a.sentiment for a in us_analyzed) / len(us_analyzed) if us_analyzed else 0.0
            hk_sentiment = sum(a.sentiment for a in hk_analyzed) / len(hk_analyzed) if hk_analyzed else 0.0

            catalysts = self._extract_catalysts(all_analyzed)
            risk_events = self._extract_risk_events(all_analyzed)

            report = MacroNewsReport(
                macro_news=[asdict(a) for a in all_analyzed[:10]],
                macro_sentiment_score=round(avg_sentiment, 3),
                macro_catalysts=catalysts,
                risk_events=risk_events,
                us_macro_news=[asdict(a) for a in us_analyzed[:5]],
                us_sentiment_score=round(us_sentiment, 3),
                hk_macro_news=[asdict(a) for a in hk_analyzed[:5]],
                hk_sentiment_score=round(hk_sentiment, 3),
            )

            # Log analysis results
            try:
                llm_logger = get_llm_analysis_logger()
                # Log both US and HK sentiment
                sentiment_data_us = {
                    'sentiment_score': round(us_sentiment, 3),
                    'sentiment_label': 'Bullish' if us_sentiment > 0.2 else ('Bearish' if us_sentiment < -0.2 else 'Neutral'),
                    'news_count': len(us_analyzed),
                    'top_catalysts': [asdict(a) for a in us_analyzed[:5]],
                }
                llm_logger.log_macro_news_analysis('US', sentiment_data_us)
            except Exception as _log_err:
                logger.debug(f"Failed to log macro news analysis: {_log_err}")
            

            # Cache
            self._cache.set(cache_key, asdict(report))

            return AgentReport(
                agent_id=self.agent_id,
                status="success",
                message=f"Macro news: {len(us_analyzed)} US + {len(hk_analyzed)} HK relevant articles",
                payload=asdict(report)
            )

        except Exception as e:
            logger.error(f"MacroNewsAgent failed: {e}", exc_info=True)
            return AgentReport(
                agent_id=self.agent_id,
                status="error",
                message=str(e),
                payload={}
            )

    async def _fetch_macro_news(self, lookback_hours: int, max_articles: int, market: str = "US") -> List[Dict[str, Any]]:
        """Fetch news from Yahoo Finance market category."""
        import yfinance as yf
        import aiohttp
        from datetime import datetime, timedelta

        articles = []
        try:
            # yfinance doesn't have a direct "market news" endpoint; we use Yahoo's RSS-like feed
            # Alternative: fetch from multiple major ticker news (SPY, QQQ, DIA) and deduplicate
            # US: S&P 500, NASDAQ, Dow ETFs; HK: Tracker Fund, H-shares, China A50 ETF
            if market == "HK":
                symbols = ["2800.HK", "2823.HK", "2822.HK"]
            else:
                symbols = ["SPY", "QQQ", "DIA"]
            cutoff_time = datetime.utcnow() - timedelta(hours=lookback_hours)

            loop = asyncio.get_event_loop()
            # We'll use the existing _fetch_news pattern; but for macro, we want broader sources
            # For now, aggregate from these ETFs' news
            all_news = []
            for sym in symbols:
                try:
                    ticker = yf.Ticker(sym)
                    news = ticker.news  # already a list of dicts
                    all_news.extend(news)
                except Exception as e:
                    logger.debug(f"Failed to fetch news for {sym}: {e}")

            # Deduplicate by title (case-insensitive)
            seen_titles = set()
            for item in all_news:
                # Handle both old API format {title, providerPublishTime, ...}
                # and new API format {id, content: {title, pubDate, summary, provider: {displayName}}}
                if "content" in item and isinstance(item["content"], dict):
                    c = item["content"]
                    title = c.get("title", "").strip()
                    summary = c.get("summary", "") or c.get("description", "")
                    pub_time_raw = c.get("pubDate") or c.get("displayTime")
                    source = (c.get("provider") or {}).get("displayName", "Yahoo Finance")
                    url = (c.get("canonicalUrl") or c.get("clickThroughUrl") or {}).get("url", "")
                else:
                    title = item.get("title", "").strip()
                    summary = item.get("summary", "")
                    pub_time_raw = item.get("providerPublishTime")
                    source = item.get("publisher", "Yahoo Finance")
                    url = item.get("link", "")

                if not title or title.lower() in seen_titles:
                    continue
                seen_titles.add(title.lower())

                # Parse published time (epoch ms or ISO string)
                if pub_time_raw:
                    if isinstance(pub_time_raw, (int, float)):
                        pub_dt = datetime.fromtimestamp(pub_time_raw)
                    else:
                        try:
                            pub_dt = datetime.fromisoformat(str(pub_time_raw).replace("Z", "+00:00"))
                            pub_dt = pub_dt.replace(tzinfo=None)  # strip tz for comparison
                        except Exception:
                            pub_dt = datetime.utcnow()
                else:
                    pub_dt = datetime.utcnow()

                if pub_dt < cutoff_time:
                    continue

                articles.append({
                    "headline": title,
                    "summary": summary,
                    "source": source,
                    "published_at": pub_dt.isoformat(),
                    "url": url
                })

                if len(articles) >= max_articles:
                    break

        except Exception as e:
            logger.error(f"Failed to fetch macro news: {e}")

        return articles

    def _filter_macro_articles(self, articles: List[Dict[str, Any]], market: str = "US") -> List[Dict[str, Any]]:
        """Filter articles to those with macro-relevant keywords."""
        # Keywords that indicate macro relevance
        macro_keywords = [
            r'\bfed\b', r'\bfederal reserve\b', r'\binterest rate\b', r'\bmonetary policy\b',
            r'\bFOMC\b', r'\binflation\b', r'\bCPI\b', r'\bNFP\b', r'\bGDP\b',
            r'\bECB\b', r'\bBOJ\b', r'\bcentral bank\b',
            r'\bgeopolitical\b', r'\btrade war\b', r'\btariff\b',
            r'\belection\b', r'\bregulation\b', r'\bSEC\b',
            r'\boil\b', r'\benergy\b', r'\bcommodity\b',
            r'\bdollar\b', r'\bUSD\b', r'\bcurrency\b',
            r'\bbudget\b', r'\btreasury\b', r'\byield curve\b',
            r'\bunemployment\b', r'\bjobless\b', r'\blayoff\b',
            r'\bsupply chain\b', r'\bchip shortage\b',
        ]
        # Add HK/China-specific keywords
        if market == "HK":
            macro_keywords += [
                r'\bHKMA\b', r'\bHang Seng\b', r'\bHSBC\b',
                r'\bPBOC\b', r"\bpeople's bank\b", r'\bRMB\b', r'\brenminbi\b',
                r'\bproperty.*HK\b', r'\bHK.*property\b',
                r'\bUSD.*HKD\b', r'\bHKD\b', r'\bpeg\b',
            ]
        pattern = re.compile('|'.join(macro_keywords), re.IGNORECASE)

        filtered = []
        for art in articles:
            text = (art.get("headline", "") + " " + art.get("summary", "")).lower()
            if pattern.search(text):
                filtered.append(art)
        return filtered

    def _analyze_article(self, article: Dict[str, Any]) -> MacroNewsItem:
        """Analyze a single article for sentiment and categorization."""
        text = article["headline"] + ". " + article.get("summary", "")

        # Sentiment
        sentiment = 0.0
        if self._vader:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
            sentiment = self._vader.polarity_scores(text)["compound"]

        # Category classification based on keywords
        category = self._categorize_article(text)

        # Impact tags
        impact_tags = self._extract_impact_tags(text)

        # Urgency: high if "breaking", "urgent", "just in", or within last 6 hours
        urgency = "medium"
        try:
            pub_dt = datetime.fromisoformat(article["published_at"].replace("Z", "+00:00"))
            age_hours = (datetime.utcnow() - pub_dt.replace(tzinfo=None)).total_seconds() / 3600
            if age_hours < 6:
                urgency = "high"
            if age_hours > 24:
                urgency = "low"
        except:
            pass

        return MacroNewsItem(
            headline=article["headline"],
            source=article.get("source", "Unknown"),
            published_at=article["published_at"],
            sentiment=sentiment,
            category=category,
            impact_tags=impact_tags,
            urgency=urgency
        )

    def _categorize_article(self, text: str) -> str:
        """Categorize article into macro theme."""
        categories = {
            "monetary_policy": [r'\bfed\b', r'\binterest rate\b', r'\bmonetary policy\b', r'\bFOMC\b', r'\byield\b', r'\becb\b', r'\bcentral bank\b', r'\bbond purchase\b', r'\bquantitative\b'],
            "geopolitical": [r'\bwar\b', r'\belection\b', r'\btrade\b', r'\bsanction\b', r'\bconflict\b'],
            "economic_data": [r'\bCPI\b', r'\bNFP\b', r'\bGDP\b', r'\bunemployment\b', r'\binflation\b'],
            "regulatory": [r'\bSEC\b', r'\bregulation\b', r'\bcompliance\b', r'\blaw\b'],
            "sector_rotation": [r'\btech\b', r'\benergy\b', r'\bfinancial\b', r'\bhealthcare\b', r'\brotation\b', r'\bproperty\b', r'\breal estate\b'],
            "hk_china": [r'\bHKMA\b', r'\bHang Seng\b', r'\bPBOC\b', r'\brenminbi\b', r'\bRMB\b', r'\bHong Kong\b', r'\bShanghai\b'],
        }
        text_lower = text.lower()
        for cat, patterns in categories.items():
            for pat in patterns:
                if re.search(pat, text_lower, re.IGNORECASE):
                    return cat
        return "other"

    def _extract_impact_tags(self, text: str) -> List[str]:
        """Extract tags indicating asset class impact."""
        tags_map = {
            "rates": [r'\brate hike\b', r'\brate cut\b', r'\byield\b'],
            "inflation": [r'\binflation\b', r'\bCPI\b', r'\bprices\b'],
            "dollar": [r'\bdollar\b', r'\bUSD\b', r'\bDXY\b'],
            "stocks": [r'\bstock\b', r'\bequity\b', r'\bmarket\b', r'\binstitutional\b'],
            "crypto": [r'\bbitcoin\b', r'\bcrypto\b', r'\bethereum\b'],
            "commodities": [r'\boil\b', r'\bgold\b', r'\bcommodity\b'],
        }
        tags = []
        text_lower = text.lower()
        for tag, patterns in tags_map.items():
            for pat in patterns:
                if re.search(pat, text_lower, re.IGNORECASE):
                    tags.append(tag)
                    break
        return list(set(tags))

    def _extract_catalysts(self, articles: List[MacroNewsItem]) -> List[str]:
        """Extract macro catalyst phrases."""
        catalysts = []
        for art in articles:
            # Simple keyword extraction from headline
            words = re.findall(r'\b[A-Za-z]{4,}\b', art.headline)
            # Add some known macro catalyst patterns
            if any(kw in art.headline.lower() for kw in ["rate decision", "inflation data", "earnings season", "fed meeting", "CPI release"]):
                catalysts.append(art.headline[:60] + "...")
        # Deduplicate
        return list(set(catalysts))[:10]

    def _extract_risk_events(self, articles: List[MacroNewsItem]) -> List[str]:
        """Identify upcoming risk events."""
        upcoming = []
        for art in articles:
            if art.urgency == "high":
                upcoming.append(f"{art.headline[:50]}... ({art.published_at})")
        return upcoming[:5]
