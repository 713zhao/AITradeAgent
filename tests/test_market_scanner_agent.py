"""
Comprehensive tests for MarketScannerAgent (3-Tier Architecture)

Tests cover:
1. Basic initialization and accessors
2. Theme scanning helpers
3. Liquidity filtering
4. Symbol ranking (composite scoring, returns tuples)
5. Tier 1: Discovery scan (run()) with rated_symbols payload
6. Tier 2: Price monitor (refresh_watchlist_prices())
7. Watchlist state management
8. Whitelist functionality
9. Error handling and edge cases
10. Integration tests (full pipeline)
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from finance_service.agents.market_scanner_agent import MarketScannerAgent
from finance_service.agents.agent_interface import AgentReport
from finance_service.core.yaml_config import YAMLConfigEngine

pytest_plugins = ('pytest_asyncio',)


# ─── Mock helpers ────────────────────────────────────────────────

def create_mock_config():
    """Create a mock YAMLConfigEngine with test data"""
    config = Mock(spec=YAMLConfigEngine)
    
    config.get.side_effect = lambda section, path, default=None: {
        ("finance", "universe/whitelist/enabled"): False,
        ("finance", "universe/whitelist/symbols"): [],
        ("finance", "universe/themes"): [
            {
                "name": "AI",
                "symbols": ["NVDA", "PLTR", "UPST"]
            },
            {
                "name": "Semiconductor",
                "symbols": ["AMD", "TSM", "ASML"]
            },
            {
                "name": "Tech",
                "symbols": ["MSFT", "GOOGL", "META"]
            }
        ],
        ("finance", "universe/all_symbols"): [
            "NVDA", "PLTR", "UPST", "AMD", "TSM", "ASML", "MSFT", "GOOGL", "META"
        ],
        ("finance", "scanner/discovery_top_n_per_theme"): 10,
        ("finance", "scanner/price_monitor_top_n"): 50,
    }.get((section, path), default)
    
    return config


def create_data_report(symbol, prices=None, volumes=None, fundamentals=None):
    """Helper to create mock DataAgent report"""
    if prices is None:
        prices = [100 + i for i in range(20)]
    if volumes is None:
        volumes = [10_000_000 + i*100_000 for i in range(20)]
    if fundamentals is None:
        fundamentals = {"pe_ratio": 25, "market_cap": 1e12}
    
    return AgentReport(
        agent_id="data_agent",
        status="success",
        message=f"Data for {symbol}",
        payload={
            "symbol": symbol,
            "dataframe": {
                i: {"close": prices[i], "volume": volumes[i]}
                for i in range(len(prices))
            },
            "fundamentals": fundamentals
        }
    )


# ─── Test Classes ────────────────────────────────────────────────

class TestMarketScannerBasics:
    """Test basic MarketScannerAgent functionality"""
    
    def test_initialization(self):
        """Test agent initialization"""
        config = create_mock_config()
        scanner = MarketScannerAgent(config)
        
        assert scanner.agent_id == "market_scanner_agent"
        assert "discover promising stocks" in scanner.goal.lower()
        assert scanner._whitelist_enabled == False
        assert scanner._watchlist == []
        assert scanner._watchlist_symbols == []
        assert scanner._last_discovery is None
    
    def test_get_available_themes(self):
        """Test getting available themes"""
        config = create_mock_config()
        scanner = MarketScannerAgent(config)
        
        themes = scanner.get_available_themes()
        
        assert len(themes) == 3
        assert "AI" in themes
        assert "Semiconductor" in themes
        assert "Tech" in themes
    
    def test_get_symbols_by_theme(self):
        """Test getting symbols for a specific theme"""
        config = create_mock_config()
        scanner = MarketScannerAgent(config)
        
        ai_symbols = scanner.get_symbols_by_theme("AI")
        
        assert len(ai_symbols) == 3
        assert "NVDA" in ai_symbols
        assert "PLTR" in ai_symbols
        assert "UPST" in ai_symbols
    
    def test_get_symbols_by_theme_case_insensitive(self):
        """Test theme lookup is case-insensitive"""
        config = create_mock_config()
        scanner = MarketScannerAgent(config)
        
        ai_symbols = scanner.get_symbols_by_theme("ai")
        
        assert len(ai_symbols) == 3
        assert "NVDA" in ai_symbols
    
    def test_get_symbols_by_invalid_theme(self):
        """Test getting symbols for non-existent theme"""
        config = create_mock_config()
        scanner = MarketScannerAgent(config)
        
        symbols = scanner.get_symbols_by_theme("NonExistent")
        
        assert symbols == []
    
    def test_get_all_symbols(self):
        """Test getting all configured symbols"""
        config = create_mock_config()
        scanner = MarketScannerAgent(config)
        
        all_symbols = scanner.get_all_symbols()
        
        assert len(all_symbols) == 9
        assert "NVDA" in all_symbols
        assert "AMD" in all_symbols
        assert "MSFT" in all_symbols
    
    def test_get_stats(self):
        """Test getting universe statistics"""
        config = create_mock_config()
        scanner = MarketScannerAgent(config)
        
        stats = scanner.get_stats()
        
        assert stats["total_symbols"] == 9
        assert stats["total_themes"] == 3
        assert len(stats["themes"]) == 3
        assert stats["whitelist_enabled"] == False


class TestThemeScanning:
    """Test theme-based symbol scanning helpers"""
    
    def test_scan_single_theme(self):
        """Test scanning a single theme"""
        config = create_mock_config()
        scanner = MarketScannerAgent(config)
        
        result = scanner.scan_theme("AI")
        
        assert result["theme"] == "AI"
        assert result["count"] == 3
        assert len(result["symbols"]) == 3
    
    def test_scan_all_themes(self):
        """Test scanning all themes"""
        config = create_mock_config()
        scanner = MarketScannerAgent(config)
        
        result = scanner.scan_all_themes()
        
        assert len(result) == 3
        assert "AI" in result
        assert result["AI"]["count"] == 3
        assert result["Semiconductor"]["count"] == 3
        assert result["Tech"]["count"] == 3
    
    def test_validate_symbols(self):
        """Test symbol validation"""
        config = create_mock_config()
        scanner = MarketScannerAgent(config)
        
        result = scanner.validate_symbols(["NVDA", "PLTR", "INVALID", "FAKE"])
        
        assert len(result["valid"]) == 2
        assert "NVDA" in result["valid"]
        assert "PLTR" in result["valid"]
        assert len(result["invalid"]) == 2
        assert "INVALID" in result["invalid"]
        assert "FAKE" in result["invalid"]


class TestLiquidityFiltering:
    """Test liquidity filtering functionality"""
    
    @pytest.mark.asyncio
    async def test_liquidity_filter_no_threshold(self):
        """Test that no filtering occurs when min_liquidity=0"""
        config = create_mock_config()
        scanner = MarketScannerAgent(config)
        
        symbols = ["NVDA", "PLTR", "AMD"]
        result = await scanner._filter_by_liquidity(symbols, 0.0)
        
        assert result == symbols
    
    @pytest.mark.asyncio
    async def test_liquidity_filter_no_data_agent(self):
        """Test that symbols pass through when no DataAgent provided"""
        config = create_mock_config()
        scanner = MarketScannerAgent(config)
        
        symbols = ["NVDA", "PLTR", "AMD"]
        result = await scanner._filter_by_liquidity(symbols, 1_000_000, None)
        
        assert result == symbols
    
    @pytest.mark.asyncio
    async def test_liquidity_filter_with_data_agent(self):
        """Test liquidity filtering with actual DataAgent"""
        config = create_mock_config()
        scanner = MarketScannerAgent(config)
        
        mock_data_agent = AsyncMock()
        
        async def mock_run(symbol, interval, use_cache, emit_events):
            if symbol == "NVDA":
                return create_data_report(symbol, volumes=[50_000_000]*20)
            elif symbol == "AMD":
                return create_data_report(symbol, volumes=[40_000_000]*20)
            else:  # PLTR
                return create_data_report(symbol, volumes=[5_000_000]*20)
        
        mock_data_agent.run = mock_run
        
        symbols = ["NVDA", "PLTR", "AMD"]
        result = await scanner._filter_by_liquidity(symbols, 30_000_000, mock_data_agent)
        
        assert "NVDA" in result
        assert "AMD" in result
        assert "PLTR" not in result


class TestSymbolRanking:
    """Test symbol ranking by composite score — now returns List[Tuple[str, float]]"""
    
    @pytest.mark.asyncio
    async def test_ranking_no_data_agent(self):
        """Test ranking returns symbols with default scores when no DataAgent"""
        config = create_mock_config()
        scanner = MarketScannerAgent(config)
        
        symbols = ["NVDA", "AMD", "PLTR"]
        result = await scanner._rank_symbols(symbols, None)
        
        # Should return list of (symbol, score) tuples
        assert len(result) == 3
        assert all(isinstance(r, tuple) and len(r) == 2 for r in result)
        # Default score is 0.5
        for sym, score in result:
            assert sym in symbols
            assert score == 0.5
    
    @pytest.mark.asyncio
    async def test_ranking_returns_tuples(self):
        """Test that _rank_symbols returns List[Tuple[str, float]]"""
        config = create_mock_config()
        scanner = MarketScannerAgent(config)
        
        mock_data_agent = AsyncMock()
        
        async def mock_run(symbol, interval, use_cache, emit_events):
            if symbol == "NVDA":
                return create_data_report(symbol, prices=[100 + i*2 for i in range(20)])
            elif symbol == "AMD":
                return create_data_report(symbol, prices=[100 + i for i in range(20)])
            else:
                return create_data_report(symbol, prices=[100 - i*0.5 for i in range(20)])
        
        mock_data_agent.run = mock_run
        
        symbols = ["NVDA", "AMD", "PLTR"]
        result = await scanner._rank_symbols(symbols, mock_data_agent)
        
        assert len(result) == 3
        # Each item is a (symbol, float) tuple
        for sym, score in result:
            assert isinstance(sym, str)
            assert isinstance(score, float)
        # Results should be sorted descending by score
        scores = [s for _, s in result]
        assert scores == sorted(scores, reverse=True)
    
    @pytest.mark.asyncio
    async def test_ranking_empty_symbols(self):
        """Test ranking with empty symbol list"""
        config = create_mock_config()
        scanner = MarketScannerAgent(config)
        
        result = await scanner._rank_symbols([], None)
        assert result == []
    
    @pytest.mark.asyncio
    async def test_ranking_data_fetch_failure(self):
        """Test ranking handles failed data fetches gracefully"""
        config = create_mock_config()
        scanner = MarketScannerAgent(config)
        
        mock_data_agent = AsyncMock()
        mock_data_agent.run.side_effect = Exception("Data fetch error")
        
        symbols = ["NVDA", "AMD", "PLTR"]
        result = await scanner._rank_symbols(symbols, mock_data_agent)
        
        # Should return all symbols with default 0.5 scores
        assert len(result) == 3
        for sym, score in result:
            assert sym in symbols
            assert score == 0.5


class TestDiscoveryScan:
    """Test Tier 1: Discovery scan (run() method)"""
    
    @pytest.mark.asyncio
    async def test_run_basic(self):
        """Test basic discovery scan"""
        config = create_mock_config()
        scanner = MarketScannerAgent(config)
        
        mock_event_bus = AsyncMock()
        scanner.event_bus = mock_event_bus
        
        report = await scanner.run(include_themes=["AI"], limit=2)
        
        assert report is not None
        assert report.agent_id == "market_scanner_agent"
        assert report.status == "opportunity"
        assert "symbols" in report.payload
        assert "rated_symbols" in report.payload
        assert "themes_scanned" in report.payload
        assert "discovery_timestamp" in report.payload
        assert report.payload["themes_scanned"] == ["AI"]
        
        # Event was published
        mock_event_bus.publish.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_run_rated_symbols_format(self):
        """Test that rated_symbols has correct structure"""
        config = create_mock_config()
        scanner = MarketScannerAgent(config)
        
        mock_event_bus = AsyncMock()
        scanner.event_bus = mock_event_bus
        
        report = await scanner.run(include_themes=["AI"])
        
        rated = report.payload["rated_symbols"]
        assert len(rated) > 0
        for item in rated:
            assert "symbol" in item
            assert "theme" in item
            assert "rating" in item
            assert "rank" in item
            assert item["theme"] == "AI"
            assert isinstance(item["rating"], float)
            assert isinstance(item["rank"], int)
    
    @pytest.mark.asyncio
    async def test_run_all_themes(self):
        """Test scanning all themes"""
        config = create_mock_config()
        scanner = MarketScannerAgent(config)
        
        mock_event_bus = AsyncMock()
        scanner.event_bus = mock_event_bus
        
        report = await scanner.run(include_themes=None)
        
        assert report is not None
        assert len(report.payload["symbols"]) == 9  # 3 per theme
        assert set(report.payload["themes_scanned"]) == {"AI", "Semiconductor", "Tech"}
    
    @pytest.mark.asyncio
    async def test_run_populates_watchlist(self):
        """Test that run() populates internal watchlist"""
        config = create_mock_config()
        scanner = MarketScannerAgent(config)
        
        mock_event_bus = AsyncMock()
        scanner.event_bus = mock_event_bus
        
        assert scanner.get_watchlist() == []
        assert scanner.get_watchlist_symbols() == []
        
        await scanner.run(include_themes=["AI"])
        
        watchlist = scanner.get_watchlist()
        assert len(watchlist) > 0
        assert all("symbol" in w for w in watchlist)
        
        symbols = scanner.get_watchlist_symbols()
        assert len(symbols) > 0
        assert all(isinstance(s, str) for s in symbols)
    
    @pytest.mark.asyncio
    async def test_run_updates_last_discovery(self):
        """Test that run() updates _last_discovery timestamp"""
        config = create_mock_config()
        scanner = MarketScannerAgent(config)
        
        mock_event_bus = AsyncMock()
        scanner.event_bus = mock_event_bus
        
        assert scanner._last_discovery is None
        
        await scanner.run(include_themes=["AI"])
        
        assert scanner._last_discovery is not None
        assert isinstance(scanner._last_discovery, str)
    
    @pytest.mark.asyncio
    async def test_run_per_theme_ranking(self):
        """Test that ranking is applied per-theme"""
        config = create_mock_config()
        scanner = MarketScannerAgent(config)
        
        mock_event_bus = AsyncMock()
        scanner.event_bus = mock_event_bus
        
        mock_data_agent = AsyncMock()
        
        async def mock_run(symbol, interval, use_cache, emit_events):
            price_base = {"NVDA": 150, "PLTR": 50, "UPST": 80,
                         "AMD": 120, "TSM": 100, "ASML": 200}.get(symbol, 100)
            return create_data_report(symbol, prices=[price_base + i for i in range(20)])
        
        mock_data_agent.run = mock_run
        
        report = await scanner.run(include_themes=None, data_agent=mock_data_agent)
        
        rated = report.payload["rated_symbols"]
        # Each theme should have entries
        themes_found = set(r["theme"] for r in rated)
        assert "AI" in themes_found
        assert "Semiconductor" in themes_found
        assert "Tech" in themes_found
    
    @pytest.mark.asyncio
    async def test_run_empty_themes(self):
        """Test handling when no themes to scan"""
        config = create_mock_config()
        scanner = MarketScannerAgent(config)
        
        mock_event_bus = AsyncMock()
        scanner.event_bus = mock_event_bus
        
        # If we pass empty include_themes, scan_by_themes will scan all (per code)
        # But if we override get_available_themes to return empty:
        scanner.get_available_themes = lambda: []
        
        report = await scanner.run(include_themes=None)
        
        assert report.payload["count"] == 0
        assert report.payload["symbols"] == []


class TestPriceMonitor:
    """Test Tier 2: Price monitor (refresh_watchlist_prices())"""
    
    @pytest.mark.asyncio
    async def test_refresh_empty_watchlist_no_held(self):
        """Test price refresh with empty watchlist and no held symbols"""
        config = create_mock_config()
        scanner = MarketScannerAgent(config)
        
        report = await scanner.refresh_watchlist_prices()
        
        assert report is not None
        assert report.agent_id == "market_scanner_agent"
        # With no symbols to refresh, should still return a report
        assert "prices" in report.payload
    
    @pytest.mark.asyncio
    async def test_refresh_with_watchlist(self):
        """Test price refresh after discovery populates watchlist"""
        config = create_mock_config()
        scanner = MarketScannerAgent(config)
        
        mock_event_bus = AsyncMock()
        scanner.event_bus = mock_event_bus
        
        # First run discovery to populate watchlist
        await scanner.run(include_themes=["AI"])
        assert len(scanner.get_watchlist_symbols()) > 0
        
        # Now refresh prices
        mock_data_agent = AsyncMock()
        
        async def mock_run(symbol, interval, use_cache, emit_events):
            return create_data_report(symbol, prices=[100 + i for i in range(5)])
        
        mock_data_agent.run = mock_run
        
        report = await scanner.refresh_watchlist_prices(data_agent=mock_data_agent)
        
        assert report.status == "success"
        assert report.payload["count"] > 0
        assert report.payload["symbols_checked"] > 0
    
    @pytest.mark.asyncio
    async def test_refresh_with_held_symbols(self):
        """Test price refresh includes held symbols not in watchlist"""
        config = create_mock_config()
        scanner = MarketScannerAgent(config)
        
        mock_event_bus = AsyncMock()
        scanner.event_bus = mock_event_bus
        
        mock_data_agent = AsyncMock()
        
        async def mock_run(symbol, interval, use_cache, emit_events):
            return create_data_report(symbol, prices=[100 + i for i in range(5)])
        
        mock_data_agent.run = mock_run
        
        # Held symbols not in the watchlist
        report = await scanner.refresh_watchlist_prices(
            data_agent=mock_data_agent,
            held_symbols={"AAPL", "AMZN"}
        )
        
        assert report is not None
        # 2 held symbols should be checked
        assert report.payload["symbols_checked"] == 2


class TestWatchlistState:
    """Test watchlist state management"""
    
    def test_initial_watchlist_empty(self):
        """Test watchlist starts empty"""
        config = create_mock_config()
        scanner = MarketScannerAgent(config)
        
        assert scanner.get_watchlist() == []
        assert scanner.get_watchlist_symbols() == []
    
    @pytest.mark.asyncio
    async def test_watchlist_populated_after_discovery(self):
        """Test watchlist populated after discovery scan"""
        config = create_mock_config()
        scanner = MarketScannerAgent(config)
        
        mock_event_bus = AsyncMock()
        scanner.event_bus = mock_event_bus
        
        await scanner.run(include_themes=["AI", "Semiconductor"])
        
        watchlist = scanner.get_watchlist()
        assert len(watchlist) > 0
        symbols = scanner.get_watchlist_symbols()
        assert len(symbols) == len(watchlist)
    
    @pytest.mark.asyncio
    async def test_watchlist_updated_on_subsequent_scan(self):
        """Test watchlist is replaced on new discovery scan"""
        config = create_mock_config()
        scanner = MarketScannerAgent(config)
        
        mock_event_bus = AsyncMock()
        scanner.event_bus = mock_event_bus
        
        # First scan: AI only
        await scanner.run(include_themes=["AI"])
        first_watchlist = scanner.get_watchlist_symbols()
        
        # Second scan: Semiconductor only
        await scanner.run(include_themes=["Semiconductor"])
        second_watchlist = scanner.get_watchlist_symbols()
        
        # Watchlist should be different (replaced, not appended)
        assert set(first_watchlist) != set(second_watchlist)
    
    def test_get_watchlist_returns_copy(self):
        """Test that get_watchlist returns a copy, not a reference"""
        config = create_mock_config()
        scanner = MarketScannerAgent(config)
        
        w1 = scanner.get_watchlist()
        w2 = scanner.get_watchlist()
        assert w1 is not w2


class TestWhitelist:
    """Test whitelist functionality"""
    
    @pytest.mark.asyncio
    async def test_whitelist_disabled(self):
        """Test that whitelist is respected when disabled — all symbols pass"""
        config = create_mock_config()
        scanner = MarketScannerAgent(config)
        
        mock_event_bus = AsyncMock()
        scanner.event_bus = mock_event_bus
        
        report = await scanner.run(include_themes=None)
        
        # All 9 symbols should be in the result
        assert len(report.payload["symbols"]) == 9
    
    @pytest.mark.asyncio
    async def test_whitelist_enabled(self):
        """Test that whitelist filters symbols when enabled"""
        config = Mock(spec=YAMLConfigEngine)
        
        config.get.side_effect = lambda section, path, default=None: {
            ("finance", "universe/whitelist/enabled"): True,
            ("finance", "universe/whitelist/symbols"): ["NVDA", "AMD", "MSFT"],
            ("finance", "universe/themes"): [
                {"name": "AI", "symbols": ["NVDA", "PLTR", "UPST"]},
                {"name": "Semiconductor", "symbols": ["AMD", "TSM", "ASML"]},
                {"name": "Tech", "symbols": ["MSFT", "GOOGL", "META"]}
            ],
            ("finance", "universe/all_symbols"): [
                "NVDA", "PLTR", "UPST", "AMD", "TSM", "ASML", "MSFT", "GOOGL", "META"
            ],
            ("finance", "scanner/discovery_top_n_per_theme"): 10,
            ("finance", "scanner/price_monitor_top_n"): 50,
        }.get((section, path), default)
        
        scanner = MarketScannerAgent(config)
        mock_event_bus = AsyncMock()
        scanner.event_bus = mock_event_bus
        
        report = await scanner.run(include_themes=None)
        
        symbols = report.payload["symbols"]
        # Only whitelisted symbols should be present
        assert "NVDA" in symbols
        assert "AMD" in symbols
        assert "MSFT" in symbols
        assert "PLTR" not in symbols
        assert "TSM" not in symbols
        assert len(symbols) == 3


class TestErrorHandling:
    """Test error handling and edge cases"""
    
    @pytest.mark.asyncio
    async def test_run_event_publish_failure(self):
        """Test handling of event publish failure"""
        config = create_mock_config()
        scanner = MarketScannerAgent(config)
        
        mock_event_bus = AsyncMock()
        mock_event_bus.publish.side_effect = Exception("Event bus error")
        scanner.event_bus = mock_event_bus
        
        with pytest.raises(Exception, match="Event bus error"):
            await scanner.run(include_themes=["AI"], limit=2)
    
    @pytest.mark.asyncio
    async def test_rank_symbols_data_fetch_failure(self):
        """Test ranking handles failed data fetches gracefully"""
        config = create_mock_config()
        scanner = MarketScannerAgent(config)
        
        mock_data_agent = AsyncMock()
        mock_data_agent.run.side_effect = Exception("Data fetch error")
        
        symbols = ["NVDA", "AMD", "PLTR"]
        result = await scanner._rank_symbols(symbols, mock_data_agent)
        
        # Should return all symbols with default scores
        assert len(result) == 3
        for sym, score in result:
            assert sym in symbols
            assert score == 0.5


class TestScoreCalculation:
    """Test individual score calculation helpers"""
    
    def test_calc_technical_score_rising_prices(self):
        """Test technical score with rising prices"""
        config = create_mock_config()
        scanner = MarketScannerAgent(config)
        
        prices = [100 + i*2 for i in range(20)]  # Rising
        score = scanner._calc_technical_score(prices)
        
        assert 0.0 <= score <= 1.0
    
    def test_calc_technical_score_falling_prices(self):
        """Test technical score with falling prices"""
        config = create_mock_config()
        scanner = MarketScannerAgent(config)
        
        prices = [200 - i*2 for i in range(20)]  # Falling
        score = scanner._calc_technical_score(prices)
        
        assert 0.0 <= score <= 1.0
    
    def test_calc_technical_score_empty(self):
        """Test technical score with insufficient data"""
        config = create_mock_config()
        scanner = MarketScannerAgent(config)
        
        score = scanner._calc_technical_score([])
        assert score == 0.5  # neutral
    
    def test_calc_momentum_score(self):
        """Test momentum score computation"""
        config = create_mock_config()
        scanner = MarketScannerAgent(config)
        
        volumes = [10_000_000 + i*100_000 for i in range(20)]
        score = scanner._calc_momentum_score(volumes)
        
        assert 0.0 <= score <= 1.0
    
    def test_calc_value_score(self):
        """Test value score computation"""
        config = create_mock_config()
        scanner = MarketScannerAgent(config)
        
        score = scanner._calc_value_score({"pe_ratio": 15})
        assert 0.0 <= score <= 1.0
    
    def test_calc_liquidity_score(self):
        """Test liquidity score computation"""
        config = create_mock_config()
        scanner = MarketScannerAgent(config)
        
        volumes = [50_000_000] * 20
        score = scanner._calc_liquidity_score(volumes)
        assert 0.0 <= score <= 1.0


class TestIntegration:
    """Integration tests — full pipeline"""
    
    @pytest.mark.asyncio
    async def test_full_scan_pipeline(self):
        """Test complete scan pipeline: scan -> filter -> rank -> limit"""
        config = create_mock_config()
        scanner = MarketScannerAgent(config)
        
        mock_event_bus = AsyncMock()
        scanner.event_bus = mock_event_bus
        
        mock_data_agent = AsyncMock()
        
        async def mock_run(symbol, interval, use_cache, emit_events):
            return create_data_report(symbol)
        
        mock_data_agent.run = mock_run
        
        # Run full pipeline with data agent
        report = await scanner.run(
            include_themes=None,
            min_liquidity=5_000_000,
            limit=2,
            data_agent=mock_data_agent
        )
        
        assert report is not None
        assert report.status == "opportunity"
        # rated_symbols should exist
        assert len(report.payload["rated_symbols"]) > 0
        # All rated items should have required fields
        for rated in report.payload["rated_symbols"]:
            assert "symbol" in rated
            assert "theme" in rated
            assert "rating" in rated
            assert "rank" in rated
    
    @pytest.mark.asyncio
    async def test_discovery_then_price_monitor(self):
        """Test Tier 1 discovery followed by Tier 2 price monitor"""
        config = create_mock_config()
        scanner = MarketScannerAgent(config)
        
        mock_event_bus = AsyncMock()
        scanner.event_bus = mock_event_bus
        
        mock_data_agent = AsyncMock()
        
        async def mock_run(symbol, interval, use_cache, emit_events):
            return create_data_report(symbol)
        
        mock_data_agent.run = mock_run
        
        # Tier 1: Discovery
        await scanner.run(include_themes=["AI"], data_agent=mock_data_agent)
        
        watchlist_symbols = scanner.get_watchlist_symbols()
        assert len(watchlist_symbols) > 0
        
        # Tier 2: Price Monitor
        report = await scanner.refresh_watchlist_prices(
            data_agent=mock_data_agent,
            held_symbols={"AAPL"}  # one held symbol not in watchlist
        )
        
        assert report is not None
        assert report.status == "success"
        # watchlist symbols + 1 held symbol
        assert report.payload["symbols_checked"] == len(watchlist_symbols) + 1


# Run all tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
