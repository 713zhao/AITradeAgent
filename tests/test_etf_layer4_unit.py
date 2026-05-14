"""Unit tests for Layer 4 ETF Intelligence — data models, universe, DB functions, helpers.

Tests are isolated: no yfinance, no Gemini, no live database required.
All external dependencies are mocked at the module boundary.

Run:
    pytest tests/test_etf_layer4_unit.py -v
"""

import json
import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from finance_service.ml.etf_models import (
    ETFRecommendation,
    ETFSnapshot,
    insert_etf_recommendation,
    insert_etf_snapshot,
    migrate_etf_tables,
    query_etf_recommendations,
    query_etf_snapshot_history,
    query_etf_snapshots,
    query_latest_etf_snapshot,
    RECOMMENDATION_TYPES,
)
from finance_service.ml.etf_universe import (
    CORRELATION_SCAN_SYMBOLS,
    ETF_METADATA,
    ETF_UNIVERSE,
    HEDGE_ETF_SYMBOLS,
    get_all_etf_symbols,
    get_etf_by_category,
    get_etf_metadata,
    get_sector_etfs,
)


class FakeDB:
    def __init__(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row


@pytest.fixture
def db():
    fake = FakeDB()
    migrate_etf_tables(fake)
    return fake


class TestETFUniverse:
    def test_all_symbols_unique(self):
        all_syms = get_all_etf_symbols()
        assert len(all_syms) == len(set(all_syms))

    def test_all_symbols_non_empty(self):
        assert len(get_all_etf_symbols()) > 100

    def test_all_symbols_uppercase(self):
        for sym in get_all_etf_symbols():
            assert sym == sym.upper()

    def test_all_universe_categories_non_empty(self):
        for cat, syms in ETF_UNIVERSE.items():
            assert len(syms) > 0

    def test_get_etf_by_category_valid(self):
        tech = get_etf_by_category("technology")
        assert len(tech) > 0

    def test_get_etf_by_category_missing(self):
        assert get_etf_by_category("nonexistent_category_xyz") == []

    def test_etf_metadata_known_symbol(self):
        meta = get_etf_metadata("SPY")
        assert meta["sector"] == "Broad Market"
        assert meta["asset_class"] == "Equity"

    def test_etf_metadata_unknown_symbol_fallback(self):
        meta = get_etf_metadata("ZZZZZ")
        assert meta["sector"] == "Unknown"

    def test_hedge_etf_symbols_non_empty(self):
        assert len(HEDGE_ETF_SYMBOLS) >= 5

    def test_correlation_scan_symbols_non_empty(self):
        assert len(CORRELATION_SCAN_SYMBOLS) >= 15

    def test_get_sector_etfs_returns_equity_categories_only(self):
        sectors = get_sector_etfs()
        assert "technology" in sectors
        assert "fixed_income_long" not in sectors


class TestETFSnapshot:
    def _make(self, **kw) -> ETFSnapshot:
        d = dict(etf_symbol="QQQ", date="2026-05-13", price=450.25, volume=50_000_000,
                 ytd_return=0.08, momentum_20d=0.05, volatility_20d=0.018,
                 dividend_yield=0.005, aum=2.5e11, sector="Technology", asset_class="Equity")
        d.update(kw)
        return ETFSnapshot(**d)

    def test_creation(self):
        s = self._make()
        assert s.etf_symbol == "QQQ"
        assert s.price == 450.25

    def test_defaults(self):
        s = ETFSnapshot(etf_symbol="SPY", date="2026-05-13")
        assert s.price == 0.0
        assert s.asset_class == "Equity"

    def test_to_db_tuple_length(self):
        assert len(self._make().to_db_tuple()) == 11

    def test_to_db_tuple_values(self):
        t = self._make().to_db_tuple()
        assert t[0] == "QQQ"
        assert t[1] == "2026-05-13"

    def test_to_dict_serializable(self):
        json.dumps(self._make().to_dict())

    def test_created_at_is_iso(self):
        s = self._make()
        datetime.fromisoformat(s.created_at)


class TestETFRecommendation:
    def _make(self, **kw) -> ETFRecommendation:
        d = dict(recommendation_date="2026-05-13", etf_symbol="TLT",
                 recommendation_type="hedge", confidence=0.85,
                 reason="Bond hedge", sector="Bonds",
                 correlation_to_portfolio=-0.35, suggested_allocation_pct=8.0,
                 win_probability_estimate=0.7, llm_response={"symbol": "TLT"})
        d.update(kw)
        return ETFRecommendation(**d)

    def test_creation(self):
        rec = self._make()
        assert rec.etf_symbol == "TLT"
        assert rec.recommendation_type == "hedge"

    def test_invalid_type_raises(self):
        with pytest.raises(AssertionError):
            self._make(recommendation_type="invalid_type")

    def test_all_valid_types(self):
        for rt in RECOMMENDATION_TYPES:
            assert self._make(recommendation_type=rt).recommendation_type == rt

    def test_to_db_tuple_length(self):
        assert len(self._make().to_db_tuple()) == 10

    def test_to_db_tuple_json_serialized(self):
        t = self._make().to_db_tuple()
        json.loads(t[9])

    def test_to_dict_serializable(self):
        json.dumps(self._make().to_dict())


class TestETFMigration:
    def test_creates_tables(self):
        db_inst = FakeDB()
        assert migrate_etf_tables(db_inst) is True
        cur = db_inst.connection.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cur.fetchall()}
        assert "etf_holdings_snapshot" in tables
        assert "etf_recommendations" in tables

    def test_idempotent(self):
        db_inst = FakeDB()
        migrate_etf_tables(db_inst)
        assert migrate_etf_tables(db_inst) is False

    def test_creates_indexes(self):
        db_inst = FakeDB()
        migrate_etf_tables(db_inst)
        cur = db_inst.connection.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = {row[0] for row in cur.fetchall()}
        assert "idx_etf_snapshot_date" in indexes
        assert "idx_etf_rec_type" in indexes


class TestETFDatabaseFunctions:
    def _snap(self, symbol="QQQ", date="2026-05-13") -> ETFSnapshot:
        return ETFSnapshot(etf_symbol=symbol, date=date, price=450.0, volume=5_000_000,
                           ytd_return=0.07, momentum_20d=0.04, volatility_20d=0.015,
                           dividend_yield=0.005, aum=2.5e11, sector="Technology")

    def _rec(self, symbol="TLT", rec_type="hedge") -> ETFRecommendation:
        return ETFRecommendation(recommendation_date="2026-05-13", etf_symbol=symbol,
                                 recommendation_type=rec_type, confidence=0.75,
                                 reason="Test", sector="Bonds")

    def test_insert_query_snapshot(self, db):
        assert insert_etf_snapshot(db, self._snap()) is True
        results = query_etf_snapshots(db, ["QQQ"], "2026-05-13")
        assert len(results) == 1
        assert results[0]["etf_symbol"] == "QQQ"

    def test_snapshot_upsert(self, db):
        insert_etf_snapshot(db, self._snap(symbol="SPY"))
        insert_etf_snapshot(db, ETFSnapshot(etf_symbol="SPY", date="2026-05-13", price=520.0))
        results = query_etf_snapshots(db, ["SPY"], "2026-05-13")
        assert len(results) == 1
        assert results[0]["price"] == pytest.approx(520.0)

    def test_query_snapshots_empty(self, db):
        assert query_etf_snapshots(db, ["ZZZ"], "2026-05-13") == []

    def test_query_snapshots_no_symbols(self, db):
        assert query_etf_snapshots(db, [], "2026-05-13") == []

    def test_query_latest_snapshot(self, db):
        for d in ["2026-05-11", "2026-05-12", "2026-05-13"]:
            insert_etf_snapshot(db, self._snap(date=d))
        latest = query_latest_etf_snapshot(db, "QQQ")
        assert latest is not None
        assert latest["date"] == "2026-05-13"

    def test_query_latest_missing(self, db):
        assert query_latest_etf_snapshot(db, "ZZZNOTTHERE") is None

    def test_insert_query_recommendation(self, db):
        assert insert_etf_recommendation(db, self._rec()) is True
        results = query_etf_recommendations(db, rec_type="hedge", limit=5)
        assert len(results) == 1
        assert results[0]["etf_symbol"] == "TLT"

    def test_query_recommendations_by_type(self, db):
        insert_etf_recommendation(db, self._rec(symbol="TLT", rec_type="hedge"))
        insert_etf_recommendation(db, self._rec(symbol="QQQ", rec_type="sector_rotation"))
        assert len(query_etf_recommendations(db, rec_type="hedge")) == 1
        assert len(query_etf_recommendations(db, rec_type=None)) == 2

    def test_query_snapshot_history(self, db):
        for day in range(1, 6):
            insert_etf_snapshot(db, ETFSnapshot(etf_symbol="GLD", date=f"2026-05-{day:02d}", price=180.0 + day))
        history = query_etf_snapshot_history(db, "GLD", days=30)
        assert len(history) == 5
        assert history[0]["date"] < history[-1]["date"]


class TestETFAgentHelpers:
    @pytest.fixture
    def agent(self):
        from finance_service.agents.etf_intelligence_agent import ETFIntelligenceAgent
        config = MagicMock()
        config.get.side_effect = lambda *args, **kw: kw.get("default")
        with patch("finance_service.agents.etf_intelligence_agent.ETFIntelligenceAgent._init_gemini_client"):
            a = ETFIntelligenceAgent(config)
        a.gemini_client = None
        return a

    def test_prices_to_returns(self, agent):
        returns = agent._prices_to_returns([100.0, 102.0, 101.0, 105.0])
        assert len(returns) == 3
        assert abs(returns[0] - 0.02) < 1e-9

    def test_prices_to_returns_single(self, agent):
        assert agent._prices_to_returns([100.0]) == []

    def test_pearson_perfect_positive(self, agent):
        a = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert abs(agent._pearson_correlation(a, a) - 1.0) < 1e-9

    def test_pearson_perfect_negative(self, agent):
        a = [1.0, 2.0, 3.0, 4.0, 5.0]
        b = [-1.0, -2.0, -3.0, -4.0, -5.0]
        assert abs(agent._pearson_correlation(a, b) - (-1.0)) < 1e-9

    def test_pearson_insufficient_data(self, agent):
        assert agent._pearson_correlation([1.0, 2.0], [1.0, 2.0]) == 0.0

    def test_parse_json_valid_array(self, agent):
        result = agent._parse_json_response('[{"symbol": "QQQ", "score": 9.0}]')
        assert isinstance(result, list)
        assert result[0]["symbol"] == "QQQ"

    def test_parse_json_embedded_in_text(self, agent):
        raw = 'Here:\n```json\n[{"symbol": "TLT"}]\n```'
        result = agent._parse_json_response(raw)
        assert isinstance(result, list)
        assert result[0]["symbol"] == "TLT"

    def test_parse_json_invalid_returns_empty(self, agent):
        assert agent._parse_json_response("Not JSON at all!") == []

    def test_sector_weights_single(self, agent):
        positions = [{"symbol": "QQQ", "current_value": 60000},
                     {"symbol": "SOXX", "current_value": 40000}]
        weights = agent._calculate_sector_weights(positions)
        assert "Technology" in weights
        assert abs(weights["Technology"] - 1.0) < 0.01

    def test_sector_weights_no_positions(self, agent):
        assert agent._calculate_sector_weights([]) == {}

    def test_sector_weights_zero_value(self, agent):
        assert agent._calculate_sector_weights([{"symbol": "QQQ", "current_value": 0}]) == {}

    def test_format_snapshot_table_empty(self, agent):
        assert "No snapshot data" in agent._format_snapshot_table([])

    def test_format_snapshot_table_with_data(self, agent):
        result = agent._format_snapshot_table([{
            "etf_symbol": "QQQ", "sector": "Technology", "price": 450.0,
            "momentum_20d": 0.05, "volatility_20d": 0.018, "ytd_return": 0.08, "aum": 2.5e11
        }])
        assert "QQQ" in result and "Technology" in result

    def test_parse_etf_recs_sector_rotation(self, agent):
        llm = json.dumps([
            {"symbol": "QQQ", "score": 9.2, "sector": "Technology",
             "reason": "Strong momentum", "allocation_pct": 15, "confidence": 0.92},
        ])
        recs = agent._parse_etf_recommendations(llm, "sector_rotation", "2026-05-13", [])
        assert len(recs) == 1
        assert recs[0].etf_symbol == "QQQ"
        assert recs[0].confidence == pytest.approx(0.92)

    def test_parse_etf_recs_caps_at_5(self, agent):
        llm = json.dumps([{"symbol": f"ETF{i}", "reason": "t", "confidence": 0.5} for i in range(10)])
        recs = agent._parse_etf_recommendations(llm, "hedge", "2026-05-13", [])
        assert len(recs) <= 5

    def test_parse_etf_recs_empty_response(self, agent):
        assert agent._parse_etf_recommendations("", "hedge", "2026-05-13", []) == []
