"""Benchmark strategies for backtest comparison.

Provides standard benchmarks:
- Buy and Hold (equal-weighted portfolio or single symbol)
- S&P 500 index (SPY)
- Equal volatility weighted portfolio
"""
import pandas as pd
import numpy as np
from typing import List, Optional
from .strategies import BacktestableStrategy


class BuyAndHoldStrategy(BacktestableStrategy):
    """Simple buy-and-hold strategy.
    
    Buys at first bar and holds until last bar.
    For multi-symbol, equal weight allocation per symbol.
    """
    def __init__(self, symbols: Optional[List[str]] = None, weight: float = 1.0):
        self.symbols = symbols  # if None, uses all symbols in data
        self.weight = weight  # fraction of capital to allocate

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        is_multi = isinstance(data.index, pd.MultiIndex)
        signals = []

        first_date = data.index.get_level_values(0).min() if is_multi else data.index.min()

        for idx, row in data.iterrows():
            date = idx[0] if is_multi else idx
            # On first date, buy; afterwards hold
            if date == first_date:
                signal_val = 1
                confidence = 1.0
            else:
                signal_val = 0
                confidence = 0.0

            # Simple stop/take not used for buy-and-hold
            signals.append({
                'signal': signal_val,
                'confidence': confidence,
                'stop_loss': None,
                'take_profit': None,
            })

        return pd.DataFrame(signals, index=data.index)


class SPYBenchmark(BacktestableStrategy):
    """Benchmark against SPY (S&P 500 ETF)"""
    def __init__(self):
        pass

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        # Buy SPY on first day, hold forever
        first_date = data.index.min()
        signals = []
        for idx, row in data.iterrows():
            date = idx[0] if isinstance(data.index, pd.MultiIndex) else idx
            signal = 1 if date == first_date else 0
            signals.append({'signal': signal, 'confidence': 1.0 if signal else 0.0, 'stop_loss': None, 'take_profit': None})
        return pd.DataFrame(signals, index=data.index)


class VolatilityTargetedStrategy(BacktestableStrategy):
    """Equal-volatility weighting: allocate more to less volatile symbols.
    Not implemented in this first pass — placeholder for future.
    """
    def __init__(self, target_vol: float = 0.20):
        self.target_vol = target_vol

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        raise NotImplementedError("Volatility targeting not yet implemented")
