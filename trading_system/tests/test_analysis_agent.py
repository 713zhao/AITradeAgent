from trading_system.agents.analysis_agent import compute_indicators


def test_uptrend_indicators(uptrend_ohlcv):
    ind = compute_indicators(uptrend_ohlcv)
    assert ind.sma_20 is not None
    assert ind.price > ind.sma_20 > ind.sma_50
    assert ind.rsi_14 is not None and ind.rsi_14 > 50


def test_downtrend_indicators(downtrend_ohlcv):
    ind = compute_indicators(downtrend_ohlcv)
    assert ind.price < ind.sma_20 < ind.sma_50
    assert ind.rsi_14 is not None and ind.rsi_14 < 50


def test_insufficient_history_returns_none_for_long_windows():
    from tests.conftest import make_ohlcv
    ohlcv = make_ohlcv("SHORT", [100, 101, 102])
    ind = compute_indicators(ohlcv)
    assert ind.sma_20 is None
    assert ind.sma_50 is None
    assert ind.price == 102
