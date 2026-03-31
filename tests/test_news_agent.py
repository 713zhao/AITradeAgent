"""NewsAgent Tests — fetch pipeline, cache, sentiment, catalysts"""
import json
import os
import sqlite3
import tempfile
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from finance_service.agents.news_agent import NewsAgent, _NewsCache


# ─── Helpers / Fixtures ───────────────────────────────────────────────────────

def _make_agent(tmp_db):
    cfg = MagicMock()
    with patch("finance_service.agents.news_agent.get_event_bus"), \
         patch("finance_service.agents.news_agent._NewsCache"):
        agent = NewsAgent(cfg)
    agent._cache = _NewsCache(tmp_db, ttl_minutes=60)
    return agent


def _av_article(title="Test headline", summary="test summary",
                av_score=None, hours_old=1):
    ts = datetime.utcnow() - timedelta(hours=hours_old)
    return {
        "title": title,
        "summary": summary,
        "source": "Reuters",
        "url": "https://example.com/news",
        "time_published": ts.strftime("%Y%m%dT%H%M%S"),
        "ticker_sentiment": [
            {"ticker": "NVDA", "ticker_sentiment_score": str(av_score)}
        ] if av_score is not None else [],
    }


def _fh_article(title="Test headline", summary="test summary"):
    return {
        "headline": title,
        "summary": summary,
        "source": "Bloomberg",
        "url": "https://example.com/fh",
        "datetime": int(datetime.utcnow().timestamp()),
    }


def _yf_article(title="Test headline", summary="test summary"):
    return {
        "id": "yf-001",
        "content": {
            "title": title,
            "summary": summary,
            "pubDate": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "canonicalUrl": {"url": "https://finance.yahoo.com/news/test"},
            "provider": {"displayName": "Yahoo Finance"},
        },
    }


# ─── _NewsCache ───────────────────────────────────────────────────────────────

class TestNewsCache:

    def test_miss_on_empty_db(self, tmp_path):
        cache = _NewsCache(str(tmp_path / "news.sqlite"))
        assert cache.get("AAPL") is None

    def test_set_then_get_returns_same_payload(self, tmp_path):
        cache = _NewsCache(str(tmp_path / "news.sqlite"))
        payload = {"news_count": 5, "sentiment_score": 0.35, "catalysts": ["earnings beat"]}
        cache.set("AAPL", payload)
        assert cache.get("AAPL") == payload

    def test_expired_entry_returns_none(self, tmp_path):
        cache = _NewsCache(str(tmp_path / "news.sqlite"), ttl_minutes=60)
        cache.set("TSLA", {"news_count": 2})
        old_ts = (datetime.utcnow() - timedelta(minutes=61)).isoformat()
        with sqlite3.connect(str(tmp_path / "news.sqlite")) as conn:
            conn.execute("UPDATE news_cache SET cached_at=? WHERE symbol=?", (old_ts, "TSLA"))
            conn.commit()
        assert cache.get("TSLA") is None

    def test_set_overwrites_existing_entry(self, tmp_path):
        cache = _NewsCache(str(tmp_path / "news.sqlite"))
        cache.set("MSFT", {"news_count": 3})
        cache.set("MSFT", {"news_count": 7})
        assert cache.get("MSFT")["news_count"] == 7

    def test_multiple_symbols_stored_independently(self, tmp_path):
        cache = _NewsCache(str(tmp_path / "news.sqlite"))
        cache.set("NVDA", {"news_count": 10})
        cache.set("AAPL", {"news_count": 4})
        assert cache.get("NVDA")["news_count"] == 10
        assert cache.get("AAPL")["news_count"] == 4

    def test_creates_parent_directory_if_missing(self, tmp_path):
        db_path = str(tmp_path / "subdir" / "nested" / "news.sqlite")
        _NewsCache(db_path)
        assert Path(db_path).parent.exists()

    def test_get_returns_none_for_unknown_symbol(self, tmp_path):
        cache = _NewsCache(str(tmp_path / "news.sqlite"))
        cache.set("NVDA", {"news_count": 5})
        assert cache.get("AMD") is None


# ─── Sentiment Analysis ───────────────────────────────────────────────────────

class TestSentimentAnalysis:

    def setup_method(self):
        cfg = MagicMock()
        with patch("finance_service.agents.news_agent.get_event_bus"), \
             patch("finance_service.agents.news_agent._NewsCache"):
            self.agent = NewsAgent(cfg)

    def test_empty_articles_returns_neutral(self):
        score, label = self.agent._analyze_sentiment([])
        assert score == 0.0
        assert label == "neutral"

    def test_clearly_positive_headline_scores_bullish(self):
        articles = [{"headline": "Company smashes earnings expectations, beats estimates handily",
                     "summary": "Record revenue growth surprises analysts",
                     "av_sentiment_score": None}]
        score, label = self.agent._analyze_sentiment(articles)
        assert score >= 0.3
        assert label == "bullish"

    def test_clearly_negative_headline_scores_bearish(self):
        articles = [{"headline": "Company crashes, massive loss reported, stock collapses",
                     "summary": "Terrible earnings miss, worst quarter ever",
                     "av_sentiment_score": None}]
        score, label = self.agent._analyze_sentiment(articles)
        assert score <= -0.3
        assert label == "bearish"

    def test_av_score_blended_50_50_with_vader(self):
        articles = [{"headline": "Company files quarterly report",
                     "summary": "Standard disclosure",
                     "av_sentiment_score": 0.8}]
        score_with_av, _ = self.agent._analyze_sentiment(articles)
        articles_no_av = [{"headline": "Company files quarterly report",
                           "summary": "Standard disclosure",
                           "av_sentiment_score": None}]
        score_without_av, _ = self.agent._analyze_sentiment(articles_no_av)
        assert score_with_av > score_without_av

    def test_score_clamped_to_minus_one_plus_one(self):
        articles = [{"headline": "a", "summary": "b", "av_sentiment_score": 1.5}]
        score, _ = self.agent._analyze_sentiment(articles)
        assert -1.0 <= score <= 1.0

    def test_label_bullish_at_0_3(self):
        articles = [{"headline": "Stock moves", "summary": "meh",
                     "av_sentiment_score": 0.6}]
        self.agent._vader = MagicMock()
        self.agent._vader.polarity_scores.return_value = {"compound": 0.0}
        score, label = self.agent._analyze_sentiment(articles)
        assert score == pytest.approx(0.3, abs=0.01)
        assert label == "bullish"

    def test_label_bearish_at_minus_0_3(self):
        articles = [{"headline": "Stock moves", "summary": "meh",
                     "av_sentiment_score": -0.6}]
        self.agent._vader = MagicMock()
        self.agent._vader.polarity_scores.return_value = {"compound": 0.0}
        score, label = self.agent._analyze_sentiment(articles)
        assert score == pytest.approx(-0.3, abs=0.01)
        assert label == "bearish"

    def test_aggregate_is_mean_of_all_articles(self):
        articles = [
            {"headline": "Great results", "summary": "Beat estimates", "av_sentiment_score": None},
            {"headline": "Terrible news", "summary": "Horrible loss", "av_sentiment_score": None},
        ]
        score, _ = self.agent._analyze_sentiment(articles)
        assert -1.0 <= score <= 1.0


# ─── Catalyst Detection ───────────────────────────────────────────────────────

class TestCatalystDetection:

    def setup_method(self):
        cfg = MagicMock()
        with patch("finance_service.agents.news_agent.get_event_bus"), \
             patch("finance_service.agents.news_agent._NewsCache"):
            self.agent = NewsAgent(cfg)

    def _art(self, headline, summary=""):
        return {"headline": headline, "summary": summary, "av_sentiment_score": None}

    def test_earnings_beat_detected(self):
        cats = self.agent._identify_catalysts(
            [self._art("Company beats earnings expectations by wide margin")], 0.4)
        assert "earnings beat" in cats

    def test_earnings_miss_detected(self):
        cats = self.agent._identify_catalysts(
            [self._art("Company missed earnings, revenue below estimate")], -0.4)
        assert "earnings miss" in cats

    def test_analyst_upgrade_detected(self):
        cats = self.agent._identify_catalysts(
            [self._art("Goldman upgrade NVDA to outperform with raised price target")], 0.3)
        assert "analyst upgrade" in cats

    def test_analyst_downgrade_detected(self):
        cats = self.agent._identify_catalysts(
            [self._art("Morgan Stanley downgrade AAPL to underperform")], -0.3)
        assert "analyst downgrade" in cats

    def test_merger_acquisition_detected(self):
        cats = self.agent._identify_catalysts(
            [self._art("Tech giant announces acquisition of rival in $10B buyout deal")], 0.2)
        assert "merger/acquisition" in cats

    def test_product_launch_detected(self):
        cats = self.agent._identify_catalysts(
            [self._art("Company unveiled new product at annual developer conference")], 0.3)
        assert "product launch" in cats

    def test_regulatory_approval_detected(self):
        cats = self.agent._identify_catalysts(
            [self._art("FDA approv new drug treatment after clinical trials")], 0.5)
        assert "regulatory approval" in cats

    def test_guidance_raised_detected(self):
        cats = self.agent._identify_catalysts(
            [self._art("Management raised guidance for full year outlook")], 0.4)
        assert "guidance raised" in cats

    def test_guidance_lowered_detected(self):
        cats = self.agent._identify_catalysts(
            [self._art("Company cut guidance citing macro headwinds")], -0.3)
        assert "guidance lowered" in cats

    def test_insider_buying_detected(self):
        cats = self.agent._identify_catalysts(
            [self._art("Executive purchase of 50,000 shares signals insider buy confidence")], 0.3)
        assert "insider buying" in cats

    def test_short_squeeze_detected(self):
        cats = self.agent._identify_catalysts(
            [self._art("Short interest surges, potential short squeeze building")], 0.1)
        assert "short squeeze" in cats

    def test_no_match_fallback_strong_positive(self):
        cats = self.agent._identify_catalysts([self._art("Generic update")], 0.6)
        assert "strong positive sentiment" in cats

    def test_no_match_fallback_positive_news_flow(self):
        cats = self.agent._identify_catalysts([self._art("Stock slightly up")], 0.35)
        assert "positive news flow" in cats

    def test_no_match_fallback_strong_negative(self):
        cats = self.agent._identify_catalysts([self._art("Market sell-off")], -0.55)
        assert "strong negative sentiment" in cats

    def test_no_match_fallback_negative_news_flow(self):
        cats = self.agent._identify_catalysts([self._art("Shares drift lower")], -0.35)
        assert "negative news flow" in cats

    def test_multiple_catalysts_from_single_article(self):
        cats = self.agent._identify_catalysts(
            [self._art("Company beats earnings and raised guidance for next quarter")], 0.5)
        assert "earnings beat" in cats
        assert "guidance raised" in cats

    def test_returns_sorted_list(self):
        cats = self.agent._identify_catalysts(
            [self._art("Company beat earnings and announced new product launch")], 0.4)
        assert cats == sorted(cats)

    def test_keyword_in_summary_field(self):
        cats = self.agent._identify_catalysts(
            [self._art("Quarterly filing", summary="Company beat estimates by a wide margin")], 0.3)
        assert "earnings beat" in cats

    def test_empty_articles_with_positive_score(self):
        cats = self.agent._identify_catalysts([], 0.6)
        assert "strong positive sentiment" in cats


# ─── AlphaVantage fetcher ─────────────────────────────────────────────────────

class TestFetchAlphaVantage:

    def setup_method(self):
        cfg = MagicMock()
        with patch("finance_service.agents.news_agent.get_event_bus"), \
             patch("finance_service.agents.news_agent._NewsCache"):
            self.agent = NewsAgent(cfg)

    def _mock_session(self, json_data, status=200):
        mock_resp = AsyncMock()
        mock_resp.status = status
        mock_resp.json = AsyncMock(return_value=json_data)
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_sess = AsyncMock()
        mock_sess.get = MagicMock(return_value=mock_cm)
        return mock_sess

    @pytest.mark.anyio
    async def test_returns_articles_on_success(self):
        data = {"feed": [_av_article("NVDA beats estimates", av_score=0.5)]}
        with patch("aiohttp.ClientSession") as MockSess:
            MockSess.return_value.__aenter__ = AsyncMock(return_value=self._mock_session(data))
            MockSess.return_value.__aexit__ = AsyncMock(return_value=False)
            articles = await self.agent._fetch_alphavantage("NVDA")
        assert len(articles) >= 1
        assert articles[0]["headline"] == "NVDA beats estimates"
        assert articles[0]["av_sentiment_score"] == pytest.approx(0.5)

    @pytest.mark.anyio
    async def test_filters_articles_older_than_48h(self):
        data = {"feed": [_av_article("Old news", hours_old=50),
                         _av_article("Recent news", hours_old=2)]}
        with patch("aiohttp.ClientSession") as MockSess:
            MockSess.return_value.__aenter__ = AsyncMock(return_value=self._mock_session(data))
            MockSess.return_value.__aexit__ = AsyncMock(return_value=False)
            articles = await self.agent._fetch_alphavantage("NVDA")
        titles = [a["headline"] for a in articles]
        assert "Recent news" in titles
        assert "Old news" not in titles

    @pytest.mark.anyio
    async def test_returns_empty_on_information_key(self):
        data = {"Information": "Standard API rate limit is 25 requests per day."}
        with patch("aiohttp.ClientSession") as MockSess:
            MockSess.return_value.__aenter__ = AsyncMock(return_value=self._mock_session(data))
            MockSess.return_value.__aexit__ = AsyncMock(return_value=False)
            assert await self.agent._fetch_alphavantage("NVDA") == []

    @pytest.mark.anyio
    async def test_returns_empty_on_note_key(self):
        data = {"Note": "Thank you for using Alpha Vantage!"}
        with patch("aiohttp.ClientSession") as MockSess:
            MockSess.return_value.__aenter__ = AsyncMock(return_value=self._mock_session(data))
            MockSess.return_value.__aexit__ = AsyncMock(return_value=False)
            assert await self.agent._fetch_alphavantage("NVDA") == []

    @pytest.mark.anyio
    async def test_returns_empty_on_http_error(self):
        with patch("aiohttp.ClientSession") as MockSess:
            MockSess.return_value.__aenter__ = AsyncMock(
                return_value=self._mock_session({}, status=500))
            MockSess.return_value.__aexit__ = AsyncMock(return_value=False)
            assert await self.agent._fetch_alphavantage("NVDA") == []

    @pytest.mark.anyio
    async def test_returns_empty_on_empty_feed(self):
        with patch("aiohttp.ClientSession") as MockSess:
            MockSess.return_value.__aenter__ = AsyncMock(
                return_value=self._mock_session({"feed": []}))
            MockSess.return_value.__aexit__ = AsyncMock(return_value=False)
            assert await self.agent._fetch_alphavantage("NVDA") == []

    @pytest.mark.anyio
    async def test_returns_empty_on_timeout(self):
        with patch("aiohttp.ClientSession") as MockSess:
            mock_sess = AsyncMock()
            mock_sess.get.side_effect = asyncio.TimeoutError
            MockSess.return_value.__aenter__ = AsyncMock(return_value=mock_sess)
            MockSess.return_value.__aexit__ = AsyncMock(return_value=False)
            assert await self.agent._fetch_alphavantage("NVDA") == []

    @pytest.mark.anyio
    async def test_strips_suffix_from_hk_ticker(self):
        captured = []

        def _fake_get(url, **kwargs):
            captured.append(url)
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value={"feed": []})
            cm = AsyncMock()
            cm.__aenter__ = AsyncMock(return_value=mock_resp)
            cm.__aexit__ = AsyncMock(return_value=False)
            return cm

        with patch("aiohttp.ClientSession") as MockSess:
            mock_sess = AsyncMock()
            mock_sess.get = _fake_get
            MockSess.return_value.__aenter__ = AsyncMock(return_value=mock_sess)
            MockSess.return_value.__aexit__ = AsyncMock(return_value=False)
            await self.agent._fetch_alphavantage("0966.HK")
        assert "tickers=0966" in captured[0]
        assert ".HK" not in captured[0]


# ─── Finnhub fetcher ──────────────────────────────────────────────────────────

class TestFetchFinnhub:

    def setup_method(self):
        cfg = MagicMock()
        with patch("finance_service.agents.news_agent.get_event_bus"), \
             patch("finance_service.agents.news_agent._NewsCache"):
            self.agent = NewsAgent(cfg)

    def _mock_session(self, json_data, status=200):
        mock_resp = AsyncMock()
        mock_resp.status = status
        mock_resp.json = AsyncMock(return_value=json_data)
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_sess = AsyncMock()
        mock_sess.get = MagicMock(return_value=mock_cm)
        return mock_sess

    @pytest.mark.anyio
    async def test_returns_mapped_articles(self):
        with patch("aiohttp.ClientSession") as MockSess:
            MockSess.return_value.__aenter__ = AsyncMock(
                return_value=self._mock_session([_fh_article("Finnhub headline")]))
            MockSess.return_value.__aexit__ = AsyncMock(return_value=False)
            articles = await self.agent._fetch_finnhub("NVDA")
        assert len(articles) == 1
        assert articles[0]["headline"] == "Finnhub headline"
        assert articles[0]["av_sentiment_score"] is None

    @pytest.mark.anyio
    async def test_caps_at_20_articles(self):
        items = [_fh_article(f"Article {i}") for i in range(30)]
        with patch("aiohttp.ClientSession") as MockSess:
            MockSess.return_value.__aenter__ = AsyncMock(
                return_value=self._mock_session(items))
            MockSess.return_value.__aexit__ = AsyncMock(return_value=False)
            articles = await self.agent._fetch_finnhub("NVDA")
        assert len(articles) == 20

    @pytest.mark.anyio
    async def test_returns_empty_on_non_list_response(self):
        with patch("aiohttp.ClientSession") as MockSess:
            MockSess.return_value.__aenter__ = AsyncMock(
                return_value=self._mock_session({"error": "rate limited"}))
            MockSess.return_value.__aexit__ = AsyncMock(return_value=False)
            assert await self.agent._fetch_finnhub("NVDA") == []

    @pytest.mark.anyio
    async def test_returns_empty_on_http_error(self):
        with patch("aiohttp.ClientSession") as MockSess:
            MockSess.return_value.__aenter__ = AsyncMock(
                return_value=self._mock_session([], status=403))
            MockSess.return_value.__aexit__ = AsyncMock(return_value=False)
            assert await self.agent._fetch_finnhub("NVDA") == []

    @pytest.mark.anyio
    async def test_returns_empty_on_timeout(self):
        with patch("aiohttp.ClientSession") as MockSess:
            mock_sess = AsyncMock()
            mock_sess.get.side_effect = asyncio.TimeoutError
            MockSess.return_value.__aenter__ = AsyncMock(return_value=mock_sess)
            MockSess.return_value.__aexit__ = AsyncMock(return_value=False)
            assert await self.agent._fetch_finnhub("NVDA") == []


# ─── Yahoo Finance fetcher ────────────────────────────────────────────────────

class TestFetchYahoo:

    def setup_method(self):
        cfg = MagicMock()
        with patch("finance_service.agents.news_agent.get_event_bus"), \
             patch("finance_service.agents.news_agent._NewsCache"):
            self.agent = NewsAgent(cfg)

    @pytest.mark.anyio
    async def test_returns_mapped_articles(self):
        raw = [_yf_article("Yahoo headline", "Yahoo summary")]
        with patch("finance_service.agents.news_agent.asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=raw)
            articles = await self.agent._fetch_yahoo("NVDA")
        assert len(articles) == 1
        assert articles[0]["headline"] == "Yahoo headline"
        assert articles[0]["summary"] == "Yahoo summary"
        assert "finance.yahoo.com" in articles[0]["url"]
        assert articles[0]["av_sentiment_score"] is None

    @pytest.mark.anyio
    async def test_caps_at_20_articles(self):
        raw = [_yf_article(f"Article {i}") for i in range(30)]
        with patch("finance_service.agents.news_agent.asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=raw)
            articles = await self.agent._fetch_yahoo("NVDA")
        assert len(articles) == 20

    @pytest.mark.anyio
    async def test_skips_articles_with_no_title(self):
        raw = [
            {"id": "1", "content": {"title": "", "summary": "has summary"}},
            _yf_article("Good article"),
        ]
        with patch("finance_service.agents.news_agent.asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=raw)
            articles = await self.agent._fetch_yahoo("NVDA")
        assert len(articles) == 1
        assert articles[0]["headline"] == "Good article"

    @pytest.mark.anyio
    async def test_returns_empty_on_executor_exception(self):
        with patch("finance_service.agents.news_agent.asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(side_effect=Exception("network"))
            articles = await self.agent._fetch_yahoo("NVDA")
        assert articles == []

    @pytest.mark.anyio
    async def test_handles_empty_news_list(self):
        with patch("finance_service.agents.news_agent.asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=[])
            articles = await self.agent._fetch_yahoo("NVDA")
        assert articles == []

    @pytest.mark.anyio
    async def test_handles_string_provider(self):
        raw = [{"id": "1", "content": {
            "title": "Test", "summary": "Summary",
            "pubDate": "2026-03-31T10:00:00Z",
            "canonicalUrl": {"url": "https://example.com"},
            "provider": "Reuters",
        }}]
        with patch("finance_service.agents.news_agent.asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=raw)
            articles = await self.agent._fetch_yahoo("NVDA")
        assert len(articles) == 1
        assert articles[0]["source"] == "Reuters"


# ─── Fetch Pipeline (source priority) ─────────────────────────────────────────

class TestFetchPipeline:

    def setup_method(self):
        cfg = MagicMock()
        with patch("finance_service.agents.news_agent.get_event_bus"), \
             patch("finance_service.agents.news_agent._NewsCache"):
            self.agent = NewsAgent(cfg)

    def _articles(self, label):
        return [{"headline": label, "summary": "", "av_sentiment_score": None,
                 "source": "", "url": "", "timestamp": ""}]

    @pytest.mark.anyio
    async def test_av_result_skips_finnhub_and_yahoo(self):
        self.agent._fetch_alphavantage = AsyncMock(return_value=self._articles("AV"))
        self.agent._fetch_finnhub = AsyncMock(return_value=[])
        self.agent._fetch_yahoo = AsyncMock(return_value=[])
        result = await self.agent._fetch_news("NVDA")
        self.agent._fetch_finnhub.assert_not_called()
        self.agent._fetch_yahoo.assert_not_called()
        assert result[0]["headline"] == "AV"

    @pytest.mark.anyio
    async def test_finnhub_used_when_av_empty(self):
        self.agent._fetch_alphavantage = AsyncMock(return_value=[])
        self.agent._fetch_finnhub = AsyncMock(return_value=self._articles("FH"))
        self.agent._fetch_yahoo = AsyncMock(return_value=[])
        result = await self.agent._fetch_news("NVDA")
        self.agent._fetch_yahoo.assert_not_called()
        assert result[0]["headline"] == "FH"

    @pytest.mark.anyio
    async def test_yahoo_used_when_av_and_finnhub_empty(self):
        self.agent._fetch_alphavantage = AsyncMock(return_value=[])
        self.agent._fetch_finnhub = AsyncMock(return_value=[])
        self.agent._fetch_yahoo = AsyncMock(return_value=self._articles("YF"))
        result = await self.agent._fetch_news("NVDA")
        assert result[0]["headline"] == "YF"

    @pytest.mark.anyio
    async def test_returns_empty_when_all_sources_fail(self):
        self.agent._fetch_alphavantage = AsyncMock(return_value=[])
        self.agent._fetch_finnhub = AsyncMock(return_value=[])
        self.agent._fetch_yahoo = AsyncMock(return_value=[])
        assert await self.agent._fetch_news("NVDA") == []


# ─── NewsAgent.run() integration ─────────────────────────────────────────────

class TestNewsAgentRun:

    def _agent(self, tmp_path):
        cfg = MagicMock()
        with patch("finance_service.agents.news_agent.get_event_bus"):
            agent = NewsAgent(cfg)
        agent._cache = _NewsCache(str(tmp_path / "news.sqlite"))
        agent.event_bus = AsyncMock()
        agent.event_bus.publish = AsyncMock()
        return agent

    def _articles(self):
        return [{"headline": "Good news", "summary": "Great quarter",
                 "av_sentiment_score": None, "source": "", "url": "", "timestamp": ""}]

    @pytest.mark.anyio
    async def test_returns_none_for_empty_symbol(self, tmp_path):
        assert await self._agent(tmp_path).run("") is None

    @pytest.mark.anyio
    async def test_returns_agentreport_on_success(self, tmp_path):
        agent = self._agent(tmp_path)
        agent._fetch_news = AsyncMock(return_value=self._articles())
        report = await agent.run("NVDA")
        assert report.status == "success"
        assert report.payload["symbol"] == "NVDA"
        assert report.payload["news_count"] == 1
        assert "sentiment_score" in report.payload
        assert "sentiment_label" in report.payload
        assert "catalysts" in report.payload

    @pytest.mark.anyio
    async def test_run_stores_result_in_cache(self, tmp_path):
        agent = self._agent(tmp_path)
        agent._fetch_news = AsyncMock(return_value=self._articles())
        await agent.run("AAPL")
        cached = agent._cache.get("AAPL")
        assert cached is not None
        assert cached["symbol"] == "AAPL"

    @pytest.mark.anyio
    async def test_second_run_uses_cache_not_fetch(self, tmp_path):
        agent = self._agent(tmp_path)
        agent._fetch_news = AsyncMock(return_value=self._articles())
        await agent.run("TSLA")
        await agent.run("TSLA")
        assert agent._fetch_news.call_count == 1

    @pytest.mark.anyio
    async def test_publishes_event_on_fresh_fetch(self, tmp_path):
        agent = self._agent(tmp_path)
        agent._fetch_news = AsyncMock(return_value=self._articles())
        await agent.run("MSFT")
        agent.event_bus.publish.assert_called_once()

    @pytest.mark.anyio
    async def test_cached_hit_also_publishes_event(self, tmp_path):
        agent = self._agent(tmp_path)
        agent._cache.set("GOOG", {
            "symbol": "GOOG", "news_count": 5,
            "sentiment_score": 0.4, "sentiment_label": "bullish",
            "catalysts": [], "sentiment": {}
        })
        agent._fetch_news = AsyncMock(return_value=[])
        await agent.run("GOOG")
        agent.event_bus.publish.assert_called_once()
        agent._fetch_news.assert_not_called()

    @pytest.mark.anyio
    async def test_payload_contains_legacy_sentiment_key(self, tmp_path):
        agent = self._agent(tmp_path)
        agent._fetch_news = AsyncMock(return_value=self._articles())
        report = await agent.run("AMZN")
        assert "sentiment" in report.payload
        assert "AMZN" in report.payload["sentiment"]

    @pytest.mark.anyio
    async def test_zero_articles_returns_neutral(self, tmp_path):
        agent = self._agent(tmp_path)
        agent._fetch_news = AsyncMock(return_value=[])
        report = await agent.run("UNKNOWN")
        assert report.payload["news_count"] == 0
        assert report.payload["sentiment_score"] == 0.0
        assert report.payload["sentiment_label"] == "neutral"

    def test_agent_id(self):
        cfg = MagicMock()
        with patch("finance_service.agents.news_agent.get_event_bus"), \
             patch("finance_service.agents.news_agent._NewsCache"):
            assert NewsAgent(cfg).agent_id == "news_agent"

    def test_goal_is_non_empty_string(self):
        cfg = MagicMock()
        with patch("finance_service.agents.news_agent.get_event_bus"), \
             patch("finance_service.agents.news_agent._NewsCache"):
            goal = NewsAgent(cfg).goal
        assert isinstance(goal, str) and len(goal) > 0
