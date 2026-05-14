"""Integration tests for Layer 4 ETF Intelligence.

Uses real in-memory SQLite, mocked yfinance, mocked Gemini, mocked Telegram.

Run:
    pytest tests/test_etf_layer4_integration.py -v
"""
import asyncio, json, sqlite3, sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from finance_service.ml.etf_models import (
    ETFRecommendation, ETFSnapshot,
    insert_etf_recommendation, insert_etf_snapshot,
    migrate_etf_tables,
    query_etf_recommendations, query_etf_snapshots, query_latest_etf_snapshot,
)


class FakeDB:
    def __init__(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row


def _make_agent(db: FakeDB):
    from finance_service.agents.etf_intelligence_agent import ETFIntelligenceAgent
    config = MagicMock()
    config.get.side_effect = lambda *args, **kw: kw.get("default")
    with patch("finance_service.agents.etf_intelligence_agent.ETFIntelligenceAgent._init_gemini_client"):
        agent = ETFIntelligenceAgent(config)
    agent.gemini_client = MagicMock()
    agent.telegram_agent = AsyncMock()
    agent._get_db = lambda: db
    return agent


def _make_yfinance_df(symbols, days=60):
    dates = pd.date_range(end=datetime.today(), periods=days, freq="B")
    rng = np.random.default_rng(42)
    close = {sym: 100 + rng.standard_normal(days).cumsum() for sym in symbols}
    volume = {sym: np.abs(rng.integers(1_000_000, 5_000_000, days)) for sym in symbols}
    close_df = pd.DataFrame(close, index=dates)
    volume_df = pd.DataFrame(volume, index=dates)
    cols = pd.MultiIndex.from_product([["Close", "Volume"], symbols])
    combined = pd.concat([close_df, volume_df], axis=1)
    combined.columns = cols
    return combined


class TestDailySnapshotIntegration:

    @pytest.fixture
    def db(self):
        f = FakeDB(); migrate_etf_tables(f); return f

    @pytest.fixture
    def agent(self, db): return _make_agent(db)

    @pytest.mark.asyncio
    async def test_snapshot_saves_to_db(self, agent, db):
        symbols = ["SPY", "QQQ", "GLD"]
        df = _make_yfinance_df(symbols)
        info = {"trailingAnnualDividendYield": 0.005, "totalAssets": 1e11, "ytdReturn": 0.08}
        with patch("yfinance.download", return_value=df), \
             patch("yfinance.Ticker", return_value=MagicMock(info=info)):
            count = await agent.run_daily_snapshot(symbols_override=symbols)
        assert count == 3
        today = datetime.today().strftime("%Y-%m-%d")
        results = query_etf_snapshots(db, symbols, today)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_snapshot_metrics_computed(self, agent, db):
        symbols = ["IVV"]
        df = _make_yfinance_df(symbols)
        info = {"trailingAnnualDividendYield": 0.005, "totalAssets": 1e11, "ytdReturn": 0.08}
        with patch("yfinance.download", return_value=df), \
             patch("yfinance.Ticker", return_value=MagicMock(info=info)):
            await agent.run_daily_snapshot(symbols_override=symbols)
        latest = query_latest_etf_snapshot(db, "IVV")
        assert latest is not None
        assert isinstance(latest["momentum_20d"], float)

    @pytest.mark.asyncio
    async def test_snapshot_handles_exception_gracefully(self, agent, db):
        with patch("yfinance.download", side_effect=Exception("network fail")):
            count = await agent.run_daily_snapshot(symbols_override=["SPY"])
        assert count == 0

    @pytest.mark.asyncio
    async def test_snapshot_upserts_on_rerun(self, agent, db):
        symbols = ["SPY"]
        df = _make_yfinance_df(symbols)
        info = {"trailingAnnualDividendYield": 0.005, "totalAssets": 1e11, "ytdReturn": 0.08}
        with patch("yfinance.download", return_value=df), \
             patch("yfinance.Ticker", return_value=MagicMock(info=info)):
            await agent.run_daily_snapshot(symbols_override=symbols)
            await agent.run_daily_snapshot(symbols_override=symbols)
        today = datetime.today().strftime("%Y-%m-%d")
        results = query_etf_snapshots(db, symbols, today)
        assert len(results) == 1  # upsert, not duplicate


class TestSectorRotationFlowIntegration:

    GEMINI_JSON = json.dumps([
        {"symbol": "QQQ", "score": 9.0, "sector": "Technology",
         "reason": "Strong momentum", "allocation_pct": 15, "confidence": 0.90},
    ])

    @pytest.fixture
    def db(self):
        f = FakeDB(); migrate_etf_tables(f)
        today = datetime.today().strftime("%Y-%m-%d")
        for sym in ["QQQ", "XLK", "XLV"]:
            insert_etf_snapshot(f, ETFSnapshot(
                etf_symbol=sym, date=today, price=200.0,
                sector="Technology" if sym != "XLV" else "Healthcare",
            ))
        return f

    @pytest.fixture
    def agent(self, db): return _make_agent(db)

    @pytest.mark.asyncio
    async def test_saves_recommendations(self, agent, db):
        agent.gemini_client.models.generate_content = MagicMock(
            return_value=MagicMock(text=self.GEMINI_JSON))
        recs = await agent.run_sector_rotation_analysis()
        assert len(recs) >= 1
        saved = query_etf_recommendations(db, rec_type="sector_rotation")
        assert len(saved) >= 1

    @pytest.mark.asyncio
    async def test_sends_telegram(self, agent, db):
        agent.gemini_client.models.generate_content = MagicMock(
            return_value=MagicMock(text=self.GEMINI_JSON))
        await agent.run_sector_rotation_analysis()
        agent.telegram_agent.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_gemini_exception_returns_empty(self, agent, db):
        agent.gemini_client.models.generate_content = MagicMock(
            side_effect=Exception("timeout"))
        recs = await agent.run_sector_rotation_analysis()
        assert recs == []
        agent.telegram_agent.send_message.assert_not_called()


class TestHedgeAnalysisFlowIntegration:

    HEDGE_JSON = json.dumps([
        {"symbol": "TLT", "weight_pct": 8, "reason": "Bond hedge",
         "hedge_type": "bonds", "confidence": 0.85},
    ])

    def _positions(self, tech_pct=65, other_pct=35):
        return [
            {"symbol": "QQQ", "current_value": tech_pct * 1000},
            {"symbol": "XLV", "current_value": other_pct * 1000},
        ]

    @pytest.fixture
    def db(self):
        f = FakeDB(); migrate_etf_tables(f)
        today = datetime.today().strftime("%Y-%m-%d")
        for sym in ["TLT", "GLD", "SH"]:
            insert_etf_snapshot(f, ETFSnapshot(etf_symbol=sym, date=today, price=100.0, sector="Bonds"))
        return f

    @pytest.fixture
    def agent(self, db):
        a = _make_agent(db); a.hedge_threshold = 0.50; return a

    @pytest.mark.asyncio
    async def test_high_concentration_triggers_hedge(self, agent, db):
        agent.gemini_client.models.generate_content = MagicMock(
            return_value=MagicMock(text=self.HEDGE_JSON))
        with patch.object(agent, "_get_portfolio_positions", return_value=self._positions(65)):
            recs = await agent.run_hedge_analysis()
        assert len(recs) >= 1
        assert all(r.recommendation_type == "hedge" for r in recs)

    @pytest.mark.asyncio
    async def test_low_concentration_skips_hedge(self, agent, db):
        with patch.object(agent, "_get_portfolio_positions", return_value=self._positions(30, 70)):
            recs = await agent.run_hedge_analysis()
        assert recs == []
        agent.telegram_agent.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_portfolio_skips_hedge(self, agent, db):
        with patch.object(agent, "_get_portfolio_positions", return_value=[]):
            recs = await agent.run_hedge_analysis()
        assert recs == []

    @pytest.mark.asyncio
    async def test_sends_telegram_when_triggered(self, agent, db):
        agent.gemini_client.models.generate_content = MagicMock(
            return_value=MagicMock(text=self.HEDGE_JSON))
        with patch.object(agent, "_get_portfolio_positions", return_value=self._positions(70)):
            await agent.run_hedge_analysis()
        agent.telegram_agent.send_message.assert_called_once()


class TestCorrelationScanFlowIntegration:

    CORR_JSON = json.dumps([
        {"symbol": "BND", "correlation": -0.12, "reason": "Diversifier",
         "confidence": 0.88, "allocation_pct": 10},
    ])

    @pytest.fixture
    def db(self):
        f = FakeDB(); migrate_etf_tables(f)
        today = datetime.today()
        rng = np.random.default_rng(0)
        for sym in ["BND", "GLD", "IEF"]:
            for i in range(40):
                d = (today - timedelta(days=40 - i)).strftime("%Y-%m-%d")
                insert_etf_snapshot(f, ETFSnapshot(
                    etf_symbol=sym, date=d,
                    price=float(100 + rng.standard_normal()),
                    sector="Bonds",
                ))
        return f

    @pytest.fixture
    def agent(self, db): return _make_agent(db)

    @pytest.mark.asyncio
    async def test_saves_correlation_recommendations(self, agent, db):
        agent._get_portfolio_return_history = MagicMock(return_value=[0.01, -0.005] * 20)
        agent.gemini_client.models.generate_content = MagicMock(
            return_value=MagicMock(text=self.CORR_JSON))
        recs = await agent.run_correlation_scan(symbols_override=["BND", "GLD", "IEF"])
        assert len(recs) >= 1
        saved = query_etf_recommendations(db, rec_type="correlation")
        assert len(saved) >= 1

    @pytest.mark.asyncio
    async def test_no_portfolio_returns_empty(self, agent, db):
        agent._get_portfolio_return_history = MagicMock(return_value=[])
        recs = await agent.run_correlation_scan(symbols_override=["BND"])
        assert recs == []

    @pytest.mark.asyncio
    async def test_sends_telegram(self, agent, db):
        agent._get_portfolio_return_history = MagicMock(return_value=[0.01] * 40)
        agent.gemini_client.models.generate_content = MagicMock(
            return_value=MagicMock(text=self.CORR_JSON))
        await agent.run_correlation_scan(symbols_override=["BND", "GLD", "IEF"])
        agent.telegram_agent.send_message.assert_called_once()


class TestTelegramNotificationIntegration:

    @pytest.fixture
    def db(self):
        f = FakeDB(); migrate_etf_tables(f); return f

    @pytest.fixture
    def agent(self, db): return _make_agent(db)

    def test_format_sector_rotation_message(self, agent):
        recs = [ETFRecommendation(
            recommendation_date="2026-05-13", etf_symbol="QQQ",
            recommendation_type="sector_rotation", confidence=0.92,
            reason="Strong tech momentum", sector="Technology",
            suggested_allocation_pct=15.0,
        )]
        msg = agent._format_sector_rotation_message(recs)
        assert "QQQ" in msg and "Technology" in msg

    def test_format_hedge_message(self, agent):
        recs = [ETFRecommendation(
            recommendation_date="2026-05-13", etf_symbol="TLT",
            recommendation_type="hedge", confidence=0.85,
            reason="Bond hedge", sector="Bonds", suggested_allocation_pct=8.0,
        )]
        msg = agent._format_hedge_message(recs, {"Technology": 0.65})
        assert "TLT" in msg

    def test_format_correlation_message(self, agent):
        recs = [ETFRecommendation(
            recommendation_date="2026-05-13", etf_symbol="BND",
            recommendation_type="correlation", confidence=0.88,
            reason="Low correlation", correlation_to_portfolio=-0.12,
        )]
        msg = agent._format_correlation_message(recs)
        assert "BND" in msg
