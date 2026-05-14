"""Feature (end-to-end) tests for Layer 4 ETF Intelligence.

Run:
    pytest tests/test_etf_layer4_feature.py -v
"""
import asyncio, json, sqlite3, sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest
import pytz

sys.path.insert(0, str(Path(__file__).parent.parent))

from finance_service.ml.etf_models import (
    ETFSnapshot, insert_etf_snapshot, migrate_etf_tables,
    query_etf_recommendations,
)
from finance_service.ml.layer4_scheduler import Layer4Scheduler


class FakeDB:
    def __init__(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row


def _make_agent(db):
    from finance_service.agents.etf_intelligence_agent import ETFIntelligenceAgent
    config = MagicMock()
    config.get.side_effect = lambda *args, **kw: kw.get("default")
    with patch("finance_service.agents.etf_intelligence_agent.ETFIntelligenceAgent._init_gemini_client"):
        agent = ETFIntelligenceAgent(config)
    agent.gemini_client = MagicMock()
    agent.telegram_agent = AsyncMock()
    agent._get_db = lambda: db
    return agent


class TestLayer4AppStartup:

    def test_etf_agent_importable(self):
        from finance_service.agents.etf_intelligence_agent import ETFIntelligenceAgent
        assert ETFIntelligenceAgent is not None

    def test_layer4_scheduler_importable(self):
        from finance_service.ml.layer4_scheduler import Layer4Scheduler
        assert Layer4Scheduler is not None

    def test_etf_models_importable(self):
        from finance_service.ml.etf_models import migrate_etf_tables, ETFSnapshot
        assert migrate_etf_tables is not None

    def test_etf_universe_importable(self):
        from finance_service.ml.etf_universe import get_all_etf_symbols, ETF_UNIVERSE
        assert len(ETF_UNIVERSE) > 0

    def test_agent_instantiation(self):
        from finance_service.agents.etf_intelligence_agent import ETFIntelligenceAgent
        config = MagicMock()
        config.get.side_effect = lambda *args, **kw: kw.get("default")
        with patch("finance_service.agents.etf_intelligence_agent.ETFIntelligenceAgent._init_gemini_client"):
            agent = ETFIntelligenceAgent(config)
        assert agent.agent_id == "etf_intelligence_agent"
        assert agent.telegram_agent is None

    def test_agent_telegram_wiring(self):
        from finance_service.agents.etf_intelligence_agent import ETFIntelligenceAgent
        config = MagicMock()
        config.get.side_effect = lambda *args, **kw: kw.get("default")
        with patch("finance_service.agents.etf_intelligence_agent.ETFIntelligenceAgent._init_gemini_client"):
            agent = ETFIntelligenceAgent(config)
        fake_tg = MagicMock()
        agent.telegram_agent = fake_tg
        assert agent.telegram_agent is fake_tg


class TestLayer4SchedulerTiming:

    @pytest.fixture
    def scheduler(self):
        return Layer4Scheduler(etf_agent=MagicMock(), timezone="UTC")

    def test_next_daily_is_future(self, scheduler):
        now = datetime.now(tz=pytz.UTC)
        assert scheduler._next_daily(21, 30, after=now) > now

    def test_next_daily_correct_time(self, scheduler):
        nxt = scheduler._next_daily(21, 30, after=datetime.now(tz=pytz.UTC))
        assert nxt.hour == 21 and nxt.minute == 30 and nxt.second == 0

    def test_next_daily_advances_when_past(self, scheduler):
        now_late = datetime.now(tz=pytz.UTC).replace(hour=22, minute=0, second=0, microsecond=0)
        nxt = scheduler._next_daily(21, 30, after=now_late)
        assert nxt > now_late and nxt.hour == 21

    def test_next_weekly_is_future(self, scheduler):
        now = datetime.now(tz=pytz.UTC)
        assert scheduler._next_weekly(0, 9, 0, after=now) > now

    def test_next_weekly_correct_weekday(self, scheduler):
        nxt = scheduler._next_weekly(0, 9, 0, after=datetime.now(tz=pytz.UTC))
        assert nxt.weekday() == 0

    def test_next_weekly_sunday(self, scheduler):
        nxt = scheduler._next_weekly(6, 20, 30, after=datetime.now(tz=pytz.UTC))
        assert nxt.weekday() == 6 and nxt.hour == 20

    def test_all_four_slots_set_after_refresh(self, scheduler):
        now = datetime.now(tz=pytz.UTC)
        scheduler._refresh_next_runs()
        for slot in [scheduler.next_snapshot, scheduler.next_hedge,
                     scheduler.next_sector_rotation, scheduler.next_correlation]:
            assert slot is not None and slot > now

    def test_different_timezone(self):
        sched = Layer4Scheduler(etf_agent=MagicMock(), timezone="Asia/Tokyo")
        now = datetime.now(tz=pytz.UTC)
        assert sched._next_daily(21, 30, after=now) > now


class TestLayer4EndToEnd:

    SECTOR_JSON = json.dumps([{"symbol": "QQQ", "score": 9.0, "sector": "Technology",
                                "reason": "Momentum", "allocation_pct": 15, "confidence": 0.90}])
    HEDGE_JSON  = json.dumps([{"symbol": "TLT", "weight_pct": 8, "reason": "Hedge",
                                "hedge_type": "bonds", "confidence": 0.85}])
    CORR_JSON   = json.dumps([{"symbol": "BND", "correlation": -0.10, "reason": "Diversifier",
                                "confidence": 0.80, "allocation_pct": 10}])

    @pytest.fixture
    def db(self):
        f = FakeDB(); migrate_etf_tables(f)
        today = datetime.today()
        rng = np.random.default_rng(7)
        # Today snapshots for sector rotation + hedge
        for sym in ["QQQ", "XLK", "XLV", "TLT", "GLD", "BND"]:
            insert_etf_snapshot(f, ETFSnapshot(
                etf_symbol=sym, date=today.strftime("%Y-%m-%d"), price=200.0,
                sector="Technology" if sym in ("QQQ", "XLK") else
                       "Healthcare" if sym == "XLV" else "Bonds",
            ))
        # History for correlation scan (BND needs >=5 days)
        for i in range(30):
            d = (today - timedelta(days=30 - i)).strftime("%Y-%m-%d")
            insert_etf_snapshot(f, ETFSnapshot(
                etf_symbol="BND", date=d,
                price=float(100 + rng.standard_normal()),
                sector="Bonds",
            ))
        return f

    @pytest.fixture
    def agent(self, db):
        a = _make_agent(db); a.hedge_threshold = 0.50; return a

    @pytest.mark.asyncio
    async def test_three_telegram_calls_in_full_pipeline(self, agent, db):
        # Sector rotation
        agent.gemini_client.models.generate_content = MagicMock(
            return_value=MagicMock(text=self.SECTOR_JSON))
        await agent.run_sector_rotation_analysis()

        # Hedge (tech heavy)
        agent.gemini_client.models.generate_content = MagicMock(
            return_value=MagicMock(text=self.HEDGE_JSON))
        with patch.object(agent, "_get_portfolio_positions",
                          return_value=[{"symbol": "QQQ", "current_value": 70000},
                                        {"symbol": "XLV", "current_value": 30000}]):
            await agent.run_hedge_analysis()

        # Correlation
        agent.gemini_client.models.generate_content = MagicMock(
            return_value=MagicMock(text=self.CORR_JSON))
        agent._get_portfolio_return_history = MagicMock(return_value=[0.01, -0.005] * 20)
        await agent.run_correlation_scan(symbols_override=["BND"])

        assert agent.telegram_agent.send_message.call_count == 3

    @pytest.mark.asyncio
    async def test_all_rec_types_stored(self, agent, db):
        agent.gemini_client.models.generate_content = MagicMock(
            return_value=MagicMock(text=self.SECTOR_JSON))
        await agent.run_sector_rotation_analysis()

        agent.gemini_client.models.generate_content = MagicMock(
            return_value=MagicMock(text=self.HEDGE_JSON))
        with patch.object(agent, "_get_portfolio_positions",
                          return_value=[{"symbol": "QQQ", "current_value": 70000},
                                        {"symbol": "XLV", "current_value": 30000}]):
            await agent.run_hedge_analysis()

        assert len(query_etf_recommendations(db, rec_type="sector_rotation")) >= 1
        assert len(query_etf_recommendations(db, rec_type="hedge")) >= 1


class TestConcentrationTrigger:

    HEDGE_JSON = json.dumps([{"symbol": "TLT", "weight_pct": 10, "reason": "Hedge",
                               "hedge_type": "bonds", "confidence": 0.85}])

    @pytest.fixture
    def db(self):
        f = FakeDB(); migrate_etf_tables(f)
        for sym in ["TLT", "GLD"]:
            insert_etf_snapshot(f, ETFSnapshot(
                etf_symbol=sym, date=datetime.today().strftime("%Y-%m-%d"),
                price=100.0, sector="Bonds"))
        return f

    @pytest.mark.parametrize("tech_pct,should_hedge", [
        (70, True), (60, True), (51, True),
        (50, False), (40, False), (30, False),
    ])
    @pytest.mark.asyncio
    async def test_boundary(self, tech_pct, should_hedge, db):
        agent = _make_agent(db)
        agent.hedge_threshold = 0.50
        agent.gemini_client.models.generate_content = MagicMock(
            return_value=MagicMock(text=self.HEDGE_JSON))
        # Distribute the remaining % across 3 sectors so no one sector exceeds threshold
        remaining = 100 - tech_pct
        positions = [
            {"symbol": "QQQ", "current_value": tech_pct * 1000},          # Technology
            {"symbol": "XLV", "current_value": remaining // 3 * 1000},    # Healthcare
            {"symbol": "XLF", "current_value": remaining // 3 * 1000},    # Financials
            {"symbol": "XLE", "current_value": (remaining - 2 * (remaining // 3)) * 1000},  # Energy
        ]
        with patch.object(agent, "_get_portfolio_positions", return_value=positions):
            recs = await agent.run_hedge_analysis()
        if should_hedge:
            assert len(recs) >= 1
        else:
            assert len(recs) == 0


class TestErrorRecovery:

    @pytest.fixture
    def db(self):
        f = FakeDB(); migrate_etf_tables(f); return f

    @pytest.fixture
    def agent(self, db): return _make_agent(db)

    @pytest.mark.asyncio
    async def test_yfinance_exception_returns_zero(self, agent, db):
        with patch("yfinance.download", side_effect=Exception("rate-limited")):
            count = await agent.run_daily_snapshot(symbols_override=["SPY"])
        assert count == 0

    @pytest.mark.asyncio
    async def test_empty_dataframe_returns_zero(self, agent, db):
        with patch("yfinance.download", return_value=pd.DataFrame()):
            count = await agent.run_daily_snapshot(symbols_override=["SPY"])
        assert count == 0

    @pytest.mark.asyncio
    async def test_gemini_timeout_returns_empty_recs(self, agent, db):
        today = datetime.today().strftime("%Y-%m-%d")
        insert_etf_snapshot(db, ETFSnapshot(etf_symbol="QQQ", date=today, price=450.0, sector="Technology"))
        agent.gemini_client.models.generate_content = MagicMock(
            side_effect=TimeoutError("Gemini timeout"))
        recs = await agent.run_sector_rotation_analysis()
        assert recs == []

    @pytest.mark.asyncio
    async def test_invalid_json_response_returns_empty(self, agent, db):
        today = datetime.today().strftime("%Y-%m-%d")
        insert_etf_snapshot(db, ETFSnapshot(etf_symbol="QQQ", date=today, price=450.0, sector="Technology"))
        agent.gemini_client.models.generate_content = MagicMock(
            return_value=MagicMock(text="Sorry, I cannot provide recommendations."))
        recs = await agent.run_sector_rotation_analysis()
        assert recs == []

    @pytest.mark.asyncio
    async def test_telegram_failure_does_not_crash(self, agent, db):
        today = datetime.today().strftime("%Y-%m-%d")
        insert_etf_snapshot(db, ETFSnapshot(etf_symbol="QQQ", date=today, price=450.0, sector="Technology"))
        agent.telegram_agent.send_message = AsyncMock(side_effect=Exception("Telegram down"))
        agent.gemini_client.models.generate_content = MagicMock(
            return_value=MagicMock(text='[{"symbol":"QQQ","score":9,"sector":"Technology","reason":"test","allocation_pct":15,"confidence":0.9}]'))
        # Should not raise
        recs = await agent.run_sector_rotation_analysis()
        assert isinstance(recs, list)

    @pytest.mark.asyncio
    async def test_scheduler_dispatch_swallows_exception(self):
        agent = MagicMock()
        agent.run_daily_snapshot = AsyncMock(side_effect=Exception("Fatal"))
        sched = Layer4Scheduler(etf_agent=agent, timezone="UTC")
        # _dispatch must not propagate
        await sched._dispatch("daily_snapshot")
