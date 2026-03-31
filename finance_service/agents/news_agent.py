import logging
import os
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone

import aiohttp
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from finance_service.core.yaml_config import YAMLConfigEngine
from finance_service.agents.agent_interface import Agent, AgentReport
from dataclasses import asdict
from finance_service.core.event_bus import Event, Events, get_event_bus

logger = logging.getLogger(__name__)

# ── API Keys (read from env; fall back to hardcoded values) ──────────────────
_AV_KEY = os.getenv("ALPHAVANTAGE_API_KEY", "2WFWVYZA0PE0AIWK")
_FH_KEY = os.getenv("FINNHUB_API_KEY", "d75t6k9r01qm4b7s4jm0d75t6k9r01qm4b7s4jmg")

# Timeout for HTTP calls (seconds)
_HTTP_TIMEOUT = aiohttp.ClientTimeout(total=15)


class NewsAgent(Agent):
    """
    News Agent - Fetches real news from Alpha Vantage (primary) with Finnhub
    fallback, performs VADER sentiment analysis, and identifies catalysts.
    """

    def __init__(self, config_engine: YAMLConfigEngine):
        self.config = config_engine
        self.event_bus = get_event_bus()
        self._vader = SentimentIntensityAnalyzer()
        logger.info("NewsAgent initialized")

    @property
    def agent_id(self) -> str:
        return "news_agent"

    @property
    def goal(self) -> str:
        return "Monitor news and sentiment for specified symbols to identify catalysts."

    # ─── Public entry point ───────────────────────────────────────────────────

    async def run(self, symbol: str) -> Optional[AgentReport]:
        if not symbol:
            logger.info("NewsAgent run: No symbol provided.")
            return None

        logger.info(f"NewsAgent: Fetching news for {symbol}")

        articles = await self._fetch_news(symbol)
        sentiment_score, sentiment_label, article_sentiments = self._analyze_sentiment(articles)
        catalysts = self._identify_catalysts(articles, sentiment_score)

        payload = {
            "symbol": symbol,
            "news_count": len(articles),
            "sentiment_score": sentiment_score,
            "sentiment_label": sentiment_label,
            "catalysts": catalysts,
            # Keep legacy key for backward compatibility
            "sentiment": {
                symbol: {
                    "overall_sentiment": sentiment_score,
                    "summary": sentiment_label,
                }
            },
        }

        message = (
            f"News analysis complete for {symbol}: {len(articles)} articles, "
            f"sentiment={sentiment_score:+.2f} ({sentiment_label}), "
            f"catalysts={catalysts}"
        )
        logger.info(message)

        report = AgentReport(
            agent_id=self.agent_id,
            status="success",
            message=message,
            payload=payload,
        )
        await self.event_bus.publish(Event(
            event_type=Events.NEWS_FETCH_COMPLETE,
            data=asdict(report),
        ))
        return report

    # ─── Fetch (Alpha Vantage primary, Finnhub fallback) ──────────────────────

    async def _fetch_news(self, symbol: str) -> List[Dict[str, Any]]:
        """Fetch recent news articles. Try Alpha Vantage first, then Finnhub."""
        articles = await self._fetch_alphavantage(symbol)
        if articles:
            logger.info(f"[NewsAgent] Alpha Vantage: {len(articles)} articles for {symbol}")
            return articles

        logger.warning(f"[NewsAgent] Alpha Vantage returned 0 articles for {symbol}; trying Finnhub")
        articles = await self._fetch_finnhub(symbol)
        logger.info(f"[NewsAgent] Finnhub: {len(articles)} articles for {symbol}")
        return articles

    async def _fetch_alphavantage(self, symbol: str) -> List[Dict[str, Any]]:
        """
        Alpha Vantage NEWS_SENTIMENT endpoint.
        Returns up to 20 articles from the last 48 h.
        Docs: https://www.alphavantage.co/documentation/#news-sentiment
        """
        # Strip exchange suffix for AV (e.g. 0966.HK → just skip; AV doesnt cover HK well)
        av_ticker = symbol.split(".")[0] if "." in symbol else symbol
        url = (
            "https://www.alphavantage.co/query"
            f"?function=NEWS_SENTIMENT"
            f"&tickers={av_ticker}"
            f"&limit=20"
            f"&apikey={_AV_KEY}"
        )
        try:
            async with aiohttp.ClientSession(timeout=_HTTP_TIMEOUT) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        logger.warning(f"[AV] HTTP {resp.status} for {symbol}")
                        return []
                    data = await resp.json(content_type=None)

            # Detect API rate limit or premium-only response
            if "Information" in data or "Note" in data:
                msg = data.get("Information") or data.get("Note", "")
                logger.warning(f"[AV] API limitation for {symbol}: {msg[:120]}")
                return []

            feed = data.get("feed", [])
            if not feed:
                return []

            cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
            articles = []
            for item in feed:
                # AV timestamp format: "20260331T130000"
                try:
                    ts = datetime.strptime(item["time_published"], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
                    if ts < cutoff:
                        continue
                except Exception:
                    pass

                # AV provides its own sentiment per ticker
                av_score = None
                for ts_obj in item.get("ticker_sentiment", []):
                    if ts_obj.get("ticker", "").upper() == av_ticker.upper():
                        try:
                            av_score = float(ts_obj.get("ticker_sentiment_score", 0))
                        except Exception:
                            pass
                        break

                articles.append({
                    "headline": item.get("title", ""),
                    "summary": item.get("summary", ""),
                    "source": item.get("source", ""),
                    "url": item.get("url", ""),
                    "timestamp": item.get("time_published", ""),
                    "av_sentiment_score": av_score,
                })
            return articles

        except asyncio.TimeoutError:
            logger.warning(f"[AV] Timeout fetching news for {symbol}")
            return []
        except Exception as e:
            logger.warning(f"[AV] Error fetching news for {symbol}: {e}")
            return []

    async def _fetch_finnhub(self, symbol: str) -> List[Dict[str, Any]]:
        """
        Finnhub company-news endpoint.
        Returns up to 20 articles from the last 3 days.
        Docs: https://finnhub.io/docs/api/company-news
        """
        fh_ticker = symbol.split(".")[0] if "." in symbol else symbol
        date_to = datetime.utcnow().strftime("%Y-%m-%d")
        date_from = (datetime.utcnow() - timedelta(days=3)).strftime("%Y-%m-%d")
        url = (
            "https://finnhub.io/api/v1/company-news"
            f"?symbol={fh_ticker}"
            f"&from={date_from}"
            f"&to={date_to}"
            f"&token={_FH_KEY}"
        )
        try:
            async with aiohttp.ClientSession(timeout=_HTTP_TIMEOUT) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        logger.warning(f"[FH] HTTP {resp.status} for {symbol}")
                        return []
                    items = await resp.json(content_type=None)

            if not isinstance(items, list):
                return []

            articles = []
            for item in items[:20]:
                articles.append({
                    "headline": item.get("headline", ""),
                    "summary": item.get("summary", ""),
                    "source": item.get("source", ""),
                    "url": item.get("url", ""),
                    "timestamp": datetime.utcfromtimestamp(item.get("datetime", 0)).isoformat(),
                    "av_sentiment_score": None,
                })
            return articles

        except asyncio.TimeoutError:
            logger.warning(f"[FH] Timeout fetching news for {symbol}")
            return []
        except Exception as e:
            logger.warning(f"[FH] Error fetching news for {symbol}: {e}")
            return []

    # ─── Sentiment ────────────────────────────────────────────────────────────

    def _analyze_sentiment(
        self, articles: List[Dict[str, Any]]
    ) -> tuple:
        """
        Run VADER on each headline+summary. If Alpha Vantage scores are present
        for an article they are averaged in (50/50 weight) for extra accuracy.
        Returns (aggregate_score, label, per_article_scores).
        """
        if not articles:
            return 0.0, "neutral", []

        scores = []
        article_sentiments = []
        for art in articles:
            text = f"{art.get('headline', '')}. {art.get('summary', '')}".strip()
            vader_score = self._vader.polarity_scores(text)["compound"]  # –1 to +1

            av_score = art.get("av_sentiment_score")
            if av_score is not None:
                # AV uses 0-based scale: >0.15=bullish, <-0.15=bearish; already on ~same scale
                merged = (vader_score + av_score) / 2.0
            else:
                merged = vader_score

            scores.append(merged)
            article_sentiments.append({
                "headline": art.get("headline", ""),
                "score": round(merged, 4),
            })

        aggregate = sum(scores) / len(scores)
        aggregate = max(-1.0, min(1.0, aggregate))

        if aggregate >= 0.3:
            label = "bullish"
        elif aggregate <= -0.3:
            label = "bearish"
        else:
            label = "neutral"

        return round(aggregate, 4), label, article_sentiments

    # ─── Catalyst Detection ───────────────────────────────────────────────────

    _CATALYST_PATTERNS: List[tuple] = [
        ("earnings beat",       ["beat", "earnings beat", "surpassed earnings", "topped estimate"]),
        ("earnings miss",       ["missed earnings", "below estimate", "disappointing earnings"]),
        ("analyst upgrade",     ["upgrade", "raised price target", "outperform", "buy rating"]),
        ("analyst downgrade",   ["downgrade", "underperform", "sell rating", "reduced target"]),
        ("merger/acquisition",  ["acqui", "merger", "takeover", "buyout"]),
        ("product launch",      ["launch", "new product", "unveiled", "announced product"]),
        ("regulatory approval", ["fda approv", "approved by", "regulatory clearance"]),
        ("guidance raised",     ["raised guidance", "raised outlook", "raised forecast"]),
        ("guidance lowered",    ["lowered guidance", "cut guidance", "reduced forecast"]),
        ("insider buying",      ["insider buy", "executive purchase", "director bought"]),
        ("short squeeze",       ["short squeeze", "short interest", "squeeze"]),
    ]

    def _identify_catalysts(
        self, articles: List[Dict[str, Any]], sentiment_score: float
    ) -> List[str]:
        """
        Scan headlines and summaries for keyword patterns to identify catalysts.
        Returns deduplicated list of catalyst names.
        """
        found: set = set()
        for art in articles:
            text = (
                f"{art.get('headline', '')} {art.get('summary', '')}"
            ).lower()
            for catalyst_name, keywords in self._CATALYST_PATTERNS:
                if any(kw in text for kw in keywords):
                    found.add(catalyst_name)

        # Generic fallback based purely on sentiment strength
        if not found:
            if sentiment_score >= 0.5:
                found.add("strong positive sentiment")
            elif sentiment_score >= 0.3:
                found.add("positive news flow")
            elif sentiment_score <= -0.5:
                found.add("strong negative sentiment")
            elif sentiment_score <= -0.3:
                found.add("negative news flow")

        return sorted(found)
