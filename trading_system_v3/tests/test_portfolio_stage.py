import pytest

from trading_system_v3.pipeline.portfolio_stage import PortfolioStage, PortfolioStore
from trading_system_v3.core.models import Action, ExecutionResult


def _mk_store(tmp_path):
    return PortfolioStore(str(tmp_path / "test.sqlite"), starting_cash=10_000.0)


def test_buy_reduces_cash_and_creates_position(tmp_path):
    store = _mk_store(tmp_path)
    exe = ExecutionResult(
        symbol="AAPL", action=Action.BUY, quantity=10, requested_price=100, filled_price=100,
        commission=1.0, slippage=0, status="filled", order_id="X1",
    )
    realized = store.apply_execution(exe, stop_loss_price=90.0)
    assert realized == 0
    assert store.cash == pytest.approx(10_000 - 1000 - 1.0)
    pos = store.positions()["AAPL"]
    assert pos.quantity == 10
    assert pos.stop_loss_price == 90.0


def test_sell_computes_realized_pnl_and_removes_position(tmp_path):
    store = _mk_store(tmp_path)
    buy = ExecutionResult(
        symbol="AAPL", action=Action.BUY, quantity=10, requested_price=100, filled_price=100,
        commission=0, slippage=0, status="filled", order_id="X1",
    )
    store.apply_execution(buy, stop_loss_price=90.0)
    sell = ExecutionResult(
        symbol="AAPL", action=Action.SELL, quantity=10, requested_price=110, filled_price=110,
        commission=0, slippage=0, status="filled", order_id="X2",
    )
    realized = store.apply_execution(sell, stop_loss_price=None)
    assert realized == pytest.approx(100.0)
    assert "AAPL" not in store.positions()
    assert store.day_realized_pnl() == pytest.approx(100.0)


def test_partial_sell_keeps_remaining_position(tmp_path):
    store = _mk_store(tmp_path)
    buy = ExecutionResult(
        symbol="AAPL", action=Action.BUY, quantity=10, requested_price=100, filled_price=100,
        commission=0, slippage=0, status="filled", order_id="X1",
    )
    store.apply_execution(buy, stop_loss_price=None)
    sell = ExecutionResult(
        symbol="AAPL", action=Action.SELL, quantity=4, requested_price=110, filled_price=110,
        commission=0, slippage=0, status="filled", order_id="X2",
    )
    store.apply_execution(sell, stop_loss_price=None)
    pos = store.positions()["AAPL"]
    assert pos.quantity == 6


def test_record_equity_reflects_positions_at_market_price(tmp_path):
    store = _mk_store(tmp_path)
    buy = ExecutionResult(
        symbol="AAPL", action=Action.BUY, quantity=10, requested_price=100, filled_price=100,
        commission=0, slippage=0, status="filled", order_id="X1",
    )
    store.apply_execution(buy, stop_loss_price=None)
    equity = store.record_equity({"AAPL": 120.0})
    assert equity == pytest.approx(9000 + 1200)


@pytest.mark.asyncio
async def test_portfolio_stage_apply_wraps_store(tmp_path):
    store = _mk_store(tmp_path)
    agent = PortfolioStage(store)
    exe = ExecutionResult(
        symbol="AAPL", action=Action.BUY, quantity=1, requested_price=100, filled_price=100,
        commission=0, slippage=0, status="filled", order_id="X1",
    )
    realized = await agent.apply(exe, stop_loss_price=None)
    assert realized == 0
