"""AnalysisAgent: turns raw OHLCV into an IndicatorSet.

Indicators are computed with plain pandas (no ta-lib/ta package
dependency) so the module has no C-extension or extra install burden.
"""
from __future__ import annotations

import pandas as pd

from trading_system.agents.base import Agent
from trading_system.core.models import AgentReport, IndicatorSet, OHLCV


def _sma(series: pd.Series, window: int) -> float | None:
    if len(series) < window:
        return None
    return float(series.rolling(window).mean().iloc[-1])


def _ema(series: pd.Series, span: int) -> float | None:
    if len(series) < span:
        return None
    return float(series.ewm(span=span, adjust=False).mean().iloc[-1])


def _rsi(series: pd.Series, window: int = 14) -> float | None:
    if len(series) < window + 1:
        return None
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window).mean()
    avg_loss = loss.rolling(window).mean()
    last_loss = avg_loss.iloc[-1]
    if last_loss == 0 or pd.isna(last_loss):
        return 100.0
    rs = avg_gain.iloc[-1] / last_loss
    return float(100 - (100 / (1 + rs)))


def _macd(series: pd.Series) -> tuple[float | None, float | None, float | None]:
    if len(series) < 26:
        return None, None, None
    ema12 = series.ewm(span=12, adjust=False).mean()
    ema26 = series.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    hist = macd_line - signal_line
    return float(macd_line.iloc[-1]), float(signal_line.iloc[-1]), float(hist.iloc[-1])


def _atr(df: pd.DataFrame, window: int = 14) -> float | None:
    if len(df) < window + 1:
        return None
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return float(tr.rolling(window).mean().iloc[-1])


def _bollinger(series: pd.Series, window: int = 20, num_std: float = 2.0) -> tuple[float | None, float | None]:
    if len(series) < window:
        return None, None
    mean = series.rolling(window).mean().iloc[-1]
    std = series.rolling(window).std().iloc[-1]
    return float(mean + num_std * std), float(mean - num_std * std)


def compute_indicators(ohlcv: OHLCV) -> IndicatorSet:
    if not ohlcv.bars:
        raise ValueError(f"No bars to analyze for {ohlcv.symbol}")

    df = pd.DataFrame(
        {
            "high": [b.high for b in ohlcv.bars],
            "low": [b.low for b in ohlcv.bars],
            "close": [b.close for b in ohlcv.bars],
        }
    )
    close = df["close"]
    macd, macd_signal, macd_hist = _macd(close)
    bb_upper, bb_lower = _bollinger(close)

    pct_5d = float(close.iloc[-1] / close.iloc[-6] - 1) if len(close) > 5 else None
    pct_20d = float(close.iloc[-1] / close.iloc[-21] - 1) if len(close) > 20 else None

    return IndicatorSet(
        symbol=ohlcv.symbol,
        as_of=ohlcv.bars[-1].date,
        price=float(close.iloc[-1]),
        sma_20=_sma(close, 20),
        sma_50=_sma(close, 50),
        sma_200=_sma(close, 200),
        ema_12=_ema(close, 12),
        ema_26=_ema(close, 26),
        rsi_14=_rsi(close, 14),
        macd=macd,
        macd_signal=macd_signal,
        macd_hist=macd_hist,
        atr_14=_atr(df, 14),
        bb_upper=bb_upper,
        bb_lower=bb_lower,
        pct_change_5d=pct_5d,
        pct_change_20d=pct_20d,
    )


class AnalysisAgent(Agent):
    @property
    def agent_id(self) -> str:
        return "analysis_agent"

    @property
    def goal(self) -> str:
        return "Compute technical indicators from OHLCV history"

    async def run(self, ohlcv: OHLCV) -> AgentReport:
        try:
            indicators = compute_indicators(ohlcv)
        except Exception as exc:
            return AgentReport(
                agent_id=self.agent_id, status="failure",
                message=f"Analysis failed for {ohlcv.symbol}: {exc}",
            )
        return AgentReport(
            agent_id=self.agent_id, status="success",
            message=f"Computed indicators for {ohlcv.symbol}",
            payload={"indicators": indicators},
        )
