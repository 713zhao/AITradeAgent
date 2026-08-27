from trading_system_v3.pipeline.analysis_stage import compute_indicators


def test_compute_indicators_basic(uptrend_ohlcv):
    ind = compute_indicators(uptrend_ohlcv)
    assert ind.symbol == "UP"
    assert ind.price > 0
    assert ind.sma_20 is not None
    assert ind.rsi_14 is not None and 0 <= ind.rsi_14 <= 100


def test_compute_indicators_requires_bars():
    from trading_system_v3.core.models import OHLCV
    import pytest
    with pytest.raises(ValueError):
        compute_indicators(OHLCV(symbol="X", interval="1d", bars=[]))
