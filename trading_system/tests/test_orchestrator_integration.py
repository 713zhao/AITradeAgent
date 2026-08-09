import pytest

from tests.conftest import make_ohlcv, _random_walk
from trading_system.agents.analysis_agent import AnalysisAgent
from trading_system.agents.data_agent import DataAgent
from trading_system.agents.execution_agent import ExecutionAgent
from trading_system.agents.portfolio_agent import PortfolioAgent, PortfolioStore
from trading_system.agents.risk_agent import RiskAgent, RiskPolicy
from trading_system.agents.scanner_agent import ScannerAgent
from trading_system.agents.strategy_agent import StrategyAgent
from trading_system.broker.paper_broker import PaperBroker
from trading_system.core.models import Action
from trading_system.orchestrator import Orchestrator


def _random_walk_series():
    return _random_walk(seed=42, drift_low=-1.0, drift_high=1.6)


class FakeProvider:
    def __init__(self, series: dict):
        self.series = series

    def fetch(self, symbol, lookback_days, interval):
        return make_ohlcv(symbol, self.series[symbol])


def _make_orchestrator(tmp_path, series, policy=None):
    provider = FakeProvider(series)
    scanner = ScannerAgent(list(series.keys()))
    data_agent = DataAgent(provider)
    analysis_agent = AnalysisAgent()
    strategy_agent = StrategyAgent(llm_client=None)
    risk_agent = RiskAgent(policy or RiskPolicy(min_confidence=0.5))
    broker = PaperBroker(slippage_bps=0.0, commission_bps=0.0)
    execution_agent = ExecutionAgent(broker)
    store = PortfolioStore(str(tmp_path / "portfolio.sqlite"), starting_cash=100_000.0)
    portfolio_agent = PortfolioAgent(store)
    return Orchestrator(
        scanner, data_agent, analysis_agent, strategy_agent, risk_agent,
        execution_agent, portfolio_agent,
    ), store


@pytest.mark.asyncio
async def test_full_pipeline_executes_buy_on_uptrend(tmp_path):
    series = {"UP": _random_walk_series()}
    orchestrator, store = _make_orchestrator(tmp_path, series)
    results = await orchestrator.run_scan_cycle()

    assert len(results) == 1
    r = results[0]
    assert r["proposal"].action == Action.BUY
    assert r["decision"].approved
    assert "execution" in r
    assert store.positions()["UP"].quantity > 0
    assert store.cash < 100_000.0


@pytest.mark.asyncio
async def test_full_pipeline_holds_on_flat_series(tmp_path):
    series = {"FLAT": [100.0] * 60}
    orchestrator, store = _make_orchestrator(tmp_path, series)
    results = await orchestrator.run_scan_cycle()

    r = results[0]
    assert r["proposal"].action == Action.HOLD
    assert "execution" not in r
    assert store.cash == 100_000.0


@pytest.mark.asyncio
async def test_full_pipeline_multiple_symbols_independent(tmp_path):
    series = {
        "UP": _random_walk_series(),
        "FLAT": [50.0] * 60,
    }
    orchestrator, store = _make_orchestrator(tmp_path, series)
    results = await orchestrator.run_scan_cycle()

    by_symbol = {r["symbol"]: r for r in results}
    assert by_symbol["UP"]["proposal"].action == Action.BUY
    assert by_symbol["FLAT"]["proposal"].action == Action.HOLD


@pytest.mark.asyncio
async def test_buy_then_sell_realizes_pnl(tmp_path):
    up_series = _random_walk_series()
    down_series = up_series + [up_series[-1] - i * 2.0 for i in range(1, 25)]

    class SwitchableProvider:
        def __init__(self):
            self.series = up_series

        def fetch(self, symbol, lookback_days, interval):
            return make_ohlcv(symbol, self.series)

    provider = SwitchableProvider()
    scanner = ScannerAgent(["REV"])
    data_agent = DataAgent(provider, ttl_seconds=0)
    analysis_agent = AnalysisAgent()
    strategy_agent = StrategyAgent(llm_client=None)
    risk_agent = RiskAgent(RiskPolicy(min_confidence=0.5))
    broker = PaperBroker(slippage_bps=0.0, commission_bps=0.0)
    execution_agent = ExecutionAgent(broker)
    store = PortfolioStore(str(tmp_path / "portfolio.sqlite"), starting_cash=100_000.0)
    portfolio_agent = PortfolioAgent(store)
    orchestrator = Orchestrator(
        scanner, data_agent, analysis_agent, strategy_agent, risk_agent,
        execution_agent, portfolio_agent,
    )

    await orchestrator.run_scan_cycle()
    assert store.positions().get("REV") is not None

    provider.series = down_series
    await orchestrator.run_scan_cycle()
    trades = store.trade_history()
    assert any(t["action"] == "SELL" for t in trades)
