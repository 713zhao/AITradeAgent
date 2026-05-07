import logging
from finance_service.core.flow_logger import flow
import os
import sqlite3
import json
import asyncio
import threading
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone

import aiohttp
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from finance_service.core.yaml_config import YAMLConfigEngine
from finance_service.agents.agent_interface import Agent, AgentReport
from dataclasses import asdict
from finance_service.core.event_bus import Event, Events, get_event_bus
from finance_service.llm import LLMManager, LLMConfig

logger = logging.getLogger(__name__)

# ── API Keys (env → hardcoded fallback) ──────────────────────────────────────
_AV_KEY  = os.getenv("ALPHAVANTAGE_API_KEY", "2WFWVYZA0PE0AIWK")
_FH_KEY  = os.getenv("FINNHUB_API_KEY", "d75t6k9r01qm4b7s4jm0d75t6k9r01qm4b7s4jmg")

# News cache TTL: fetch at most once per hour per symbol
_NEWS_CACHE_TTL_MINUTES = 60

_HTTP_TIMEOUT = aiohttp.ClientTimeout(total=15)


# ── Simple SQLite news cache ──────────────────────────────────────────────────

class _NewsCache:
    """
    Lightweight SQLite cache for news payloads.
    Stores the full serialised payload per symbol with a TTL.
    Thread-safe; the same DB file as other storage is NOT used to keep
    concerns separate (news_cache.sqlite lives in finance_service/storage/).
    """

    def __init__(self, db_path: str, ttl_minutes: int = _NEWS_CACHE_TTL_MINUTES):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.ttl_minutes = ttl_minutes
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS news_cache (
                    symbol      TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    cached_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def get(self, symbol: str) -> Optional[Dict]:
        """Return cached payload if still fresh, else None."""
        cutoff = datetime.utcnow() - timedelta(minutes=self.ttl_minutes)
        with self._lock:
            with sqlite3.connect(str(self.db_path)) as conn:
                row = conn.execute(
                    "SELECT payload_json, cached_at FROM news_cache WHERE symbol = ?",
                    (symbol,)
                ).fetchone()
        if not row:
            return None
        cached_at = datetime.fromisoformat(row[1])
        if cached_at < cutoff:
            return None
        age_min = int((datetime.utcnow() - cached_at).total_seconds() / 60)
        logger.info(f"[NewsCache] HIT for {symbol} (age: {age_min} min)")
        return json.loads(row[0])

    def set(self, symbol: str, payload: Dict) -> None:
        with self._lock:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute("""
                    INSERT INTO news_cache (symbol, payload_json, cached_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(symbol) DO UPDATE SET
                        payload_json = excluded.payload_json,
                        cached_at    = excluded.cached_at
                """, (symbol, json.dumps(payload), datetime.utcnow().isoformat()))
                conn.commit()
        logger.info(f"[NewsCache] Stored {symbol} ({payload.get('news_count',0)} articles)")


# ── NewsAgent ─────────────────────────────────────────────────────────────────

class NewsAgent(Agent):
    """
    News Agent — fetches real news via three free sources (priority order):
      1. Alpha Vantage NEWS_SENTIMENT  (quota: 25 req/day on free tier)
      2. Finnhub company-news          (free tier, generous rate limit)
      3. Yahoo Finance via yfinance    (no key, no quota)

    Results are cached per-symbol for 60 minutes to avoid exhausting API
    quotas during bulk scans (50 symbols × multiple pipeline runs).
    Sentiment is computed with VADER; catalysts are detected via keywords.
    """

    def __init__(self, config_engine: YAMLConfigEngine):
        self.config = config_engine
        self.event_bus = get_event_bus()
        self._vader = SentimentIntensityAnalyzer()
        _cache_path = os.path.join(
            os.path.dirname(__file__), "..", "storage", "news_cache.sqlite"
        )
        self._cache = _NewsCache(os.path.abspath(_cache_path))
        self._llm_manager: Optional[LLMManager] = None
        self._init_llm()
        logger.info("NewsAgent initialized")

    @property
    def agent_id(self) -> str:
        return "news_agent"

    @property
    def goal(self) -> str:
        return "Monitor news and sentiment for specified symbols to identify catalysts."

    def _init_llm(self):
        """Initialize LLM if configured and enabled for sentiment enhancement."""
        try:
            llm_enabled = self.config.get("llm", "enabled", default=False)
            if not llm_enabled:
                logger.debug("LLM disabled; NewsAgent will use VADER only")
                return

            module_enabled = self.config.get("llm", "modules/news_sentiment/enabled", default=False)
            if not module_enabled:
                logger.debug("News sentiment LLM module disabled")
                return

            llm_config = LLMConfig(
                provider=self.config.get("llm", "provider", default="openrouter"),
                api_key_env=self.config.get("llm", "api_key_env", default="OPENROUTER_API_KEY"),
                base_url=self.config.get("llm", "base_url", default=None),
                default_model=self.config.get("llm", "modules/news_sentiment/model",
                                              default=self.config.get("llm", "model", default="openrouter/auto")),
                temperature=self.config.get("llm", "modules/news_sentiment/temperature", default=0.4),
                max_tokens=1000,
                timeout=self.config.get("llm", "timeout", default=30),
                max_retries=self.config.get("llm", "max_retries", default=3),
            )

            # Override from environment variables if present
            if os.getenv("LLM_PROVIDER"):
                llm_config.provider = os.getenv("LLM_PROVIDER")
            if os.getenv("GOOGLE_API_KEY"):
                llm_config.api_key_env = "GOOGLE_API_KEY"
            if os.getenv("TA_DEEP_THINK_MODEL"):
                llm_config.default_model = os.getenv("TA_DEEP_THINK_MODEL")

            self._llm_manager = LLMManager(llm_config)
            if self._llm_manager.validate():
                logger.info("NewsAgent LLM initialized for sentiment enhancement")
            else:
                logger.warning("NewsAgent LLM validation failed; using VADER only")
                self._llm_manager = None
        except Exception as e:
            logger.debug(f"Failed to init LLM for NewsAgent: {e}")

    # ─── Public entry point ───────────────────────────────────────────────────

    async def run(self, symbol: str) -> Optional[AgentReport]:
        if not symbol:
            logger.info("NewsAgent run: No symbol provided.")
            return None

        # ── Cache check ──────────────────────────────────────────────────────
        cached = self._cache.get(symbol)
        if cached is not None:
            report = AgentReport(
                agent_id=self.agent_id,
                status="success",
                message=f"News (cached) for {symbol}: {cached.get('news_count',0)} articles",
                payload=cached,
            )
            flow("NewsAgent", "DONE", f"{symbol} → sentiment={cached.get('sentiment_score',0):+.2f} [{cached.get('sentiment_label','?')}] [CACHE]")
            await self.event_bus.publish(Event(
                event_type=Events.NEWS_FETCH_COMPLETE,
                data=asdict(report),
            ))
            return report

        flow("NewsAgent", "START", f"{symbol} [fresh fetch]")
        logger.info(f"NewsAgent: Fetching fresh news for {symbol}")

        articles = await self._fetch_news(symbol)
        sentiment_score, sentiment_label = self._analyze_sentiment(articles)
        catalysts = self._identify_catalysts(articles, sentiment_score)

        payload = {
            "symbol": symbol,
            "news_count": len(articles),
            "sentiment_score": sentiment_score,
            "sentiment_label": sentiment_label,
            "catalysts": catalysts,
            # Legacy key consumed by StrategyAgent and Telegram notification
            "sentiment": {
                symbol: {
                    "overall_sentiment": sentiment_score,
                    "summary": sentiment_label,
                }
            },
        }

        # ── Store in cache ───────────────────────────────────────────────────
        self._cache.set(symbol, payload)

        message = (
            f"News analysis complete for {symbol}: {len(articles)} articles, "
            f"sentiment={sentiment_score:+.2f} ({sentiment_label}), "
            f"catalysts={catalysts}"
        )
        flow("NewsAgent", "DONE", f"{symbol} → sentiment={sentiment_score:+.2f} [{sentiment_label}] {len(articles)} articles [FRESH]")
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

    # ─── Fetch pipeline ───────────────────────────────────────────────────────

    async def _fetch_news(self, symbol: str) -> List[Dict[str, Any]]:
        """Try sources in priority order; return first non-empty result."""
        # 1. Alpha Vantage
        articles = await self._fetch_alphavantage(symbol)
        if articles:
            logger.info(f"[NewsAgent] AlphaVantage: {len(articles)} articles for {symbol}")
            return articles

        logger.debug(f"[NewsAgent] AV empty for {symbol}; trying Finnhub")

        # 2. Finnhub
        articles = await self._fetch_finnhub(symbol)
        if articles:
            logger.info(f"[NewsAgent] Finnhub: {len(articles)} articles for {symbol}")
            return articles

        logger.debug(f"[NewsAgent] Finnhub empty for {symbol}; trying Yahoo Finance")

        # 3. Yahoo Finance (no API key, no quota — always available)
        articles = await self._fetch_yahoo(symbol)
        if articles:
            logger.info(f"[NewsAgent] Yahoo Finance: {len(articles)} articles for {symbol}")
        return articles

    # ── Source 1: Alpha Vantage ───────────────────────────────────────────────

    async def _fetch_alphavantage(self, symbol: str) -> List[Dict[str, Any]]:
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
                try:
                    ts = datetime.strptime(
                        item["time_published"], "%Y%m%dT%H%M%S"
                    ).replace(tzinfo=timezone.utc)
                    if ts < cutoff:
                        continue
                except Exception:
                    pass

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
            logger.warning(f"[AV] Timeout for {symbol}")
            return []
        except Exception as e:
            logger.warning(f"[AV] Error for {symbol}: {e}")
            return []

    # ── Source 2: Finnhub ─────────────────────────────────────────────────────

    async def _fetch_finnhub(self, symbol: str) -> List[Dict[str, Any]]:
        fh_ticker = symbol.split(".")[0] if "." in symbol else symbol
        date_to   = datetime.utcnow().strftime("%Y-%m-%d")
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

            return [
                {
                    "headline": item.get("headline", ""),
                    "summary": item.get("summary", ""),
                    "source": item.get("source", ""),
                    "url": item.get("url", ""),
                    "timestamp": datetime.utcfromtimestamp(
                        item.get("datetime", 0)
                    ).isoformat(),
                    "av_sentiment_score": None,
                }
                for item in items[:20]
            ]

        except asyncio.TimeoutError:
            logger.warning(f"[FH] Timeout for {symbol}")
            return []
        except Exception as e:
            logger.warning(f"[FH] Error for {symbol}: {e}")
            return []

    # ── Source 3: Yahoo Finance (yfinance, no key) ────────────────────────────

    async def _fetch_yahoo(self, symbol: str) -> List[Dict[str, Any]]:
        """
        Uses yfinance Ticker.news — no API key, no daily quota.
        Runs the blocking yfinance call in a thread pool to avoid blocking
        the async event loop.
        """
        def _blocking_fetch():
            try:
                import yfinance as yf
                ticker = yf.Ticker(symbol)
                return ticker.news or []
            except Exception as e:
                logger.warning(f"[YF] Error for {symbol}: {e}")
                return []

        try:
            loop = asyncio.get_event_loop()
            raw_items = await loop.run_in_executor(None, _blocking_fetch)
        except Exception as e:
            logger.warning(f"[YF] Executor error for {symbol}: {e}")
            return []

        articles = []
        for item in raw_items[:20]:
            content = item.get("content", {})
            headline = content.get("title") or item.get("title", "")
            summary  = content.get("summary") or content.get("description", "")
            source   = (content.get("provider") or {}).get("displayName", "") \
                       if isinstance(content.get("provider"), dict) \
                       else str(content.get("provider", ""))
            pub_date = content.get("pubDate", "")
            url_obj  = content.get("canonicalUrl") or content.get("clickThroughUrl") or {}
            url      = url_obj.get("url", "") if isinstance(url_obj, dict) else str(url_obj)

            if not headline:
                continue
            articles.append({
                "headline": headline,
                "summary": summary,
                "source": source,
                "url": url,
                "timestamp": pub_date,
                "av_sentiment_score": None,
            })
        return articles

    # ─── Sentiment ────────────────────────────────────────────────────────────

    def _analyze_sentiment(
        self, articles: List[Dict[str, Any]]
    ) -> tuple:
        if not articles:
            return 0.0, "neutral"

        scores = []
        for art in articles:
            text = f"{art.get('headline', '')}. {art.get('summary', '')}".strip()
            vader_score = self._vader.polarity_scores(text)["compound"]
            av_score = art.get("av_sentiment_score")
            merged = (vader_score + av_score) / 2.0 if av_score is not None else vader_score
            scores.append(merged)

        aggregate = max(-1.0, min(1.0, sum(scores) / len(scores)))
        label = "bullish" if aggregate >= 0.3 else ("bearish" if aggregate <= -0.3 else "neutral")
        return round(aggregate, 4), label

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
        found: set = set()
        for art in articles:
            text = f"{art.get('headline', '')} {art.get('summary', '')}".lower()
            for catalyst_name, keywords in self._CATALYST_PATTERNS:
                if any(kw in text for kw in keywords):
                    found.add(catalyst_name)

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
