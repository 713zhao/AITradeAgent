"""Base classes for backtestable strategies.

All backtesting strategies must implement `BacktestableStrategy` interface.
Adapters convert existing strategies (RuleStrategy) to backtestable form.
"""
from abc import ABC, abstractmethod
import pandas as pd
from dataclasses import dataclass
from typing import Dict, Any, Optional, List

@dataclass
class Signal:
    """Trading signal output by strategy"""
    symbol: str
    timestamp: pd.Timestamp
    action: int  # 1 = BUY, -1 = SELL, 0 = HOLD
    confidence: float  # 0-1
    price: float  # target entry price
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    metadata: Dict[str, Any] = None


class BacktestableStrategy(ABC):
    """Abstract base for strategies used in backtesting.

    Must implement `generate_signals()` which returns a DataFrame with
    columns: ['signal', 'confidence', 'stop_loss', 'take_profit']
    Indexed by (date, symbol) for multi-symbol support.
    """

    @abstractmethod
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Vectorized signal generation for all symbols and dates.

        Args:
            data: DataFrame with OHLCV data. For multi-symbol, index is (date, symbol).

        Returns:
            DataFrame with same index as data, containing:
            - signal: -1, 0, 1
            - confidence: 0-1
            - stop_loss: price level (optional)
            - take_profit: price level (optional)
        """
        pass


class RuleStrategyBacktest(BacktestableStrategy):
    """Adapter for RuleStrategy to backtesting interface.

    Wraps the existing RuleStrategy from finance_service.agents.strategy_agent
    and calls its evaluate_entry/evaluate_exit methods on each bar.
    Note: This is a per-bar iterative approach; could be vectorized if needed.
    """
    def __init__(self, rules_config: List[Dict]):
        from finance_service.agents.strategy_agent import RuleStrategy
        self.rule_strategy = RuleStrategy(rules_config)

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Iterate over each row and evaluate rules.
        Returns DataFrame with signals.
        """
        signals = []
        # Determine if multi-index
        is_multi = isinstance(data.index, pd.MultiIndex)

        for idx, row in data.iterrows():
            # Extract symbol
            if is_multi:
                date, symbol = idx
            else:
                date = idx
                symbol = None

            # Build IndicatorsSnapshot-like object from row
            # For simplicity, we'll create a simple object with .indicators dict
            class MockIndicators:
                def __init__(self, row):
                    self._row = row
                def get(self, name, default=None):
                    return self._row.get(name, default)

            indicators = MockIndicators(row)

            # Evaluate entry
            should_buy, confidence, entry_triggers = self.rule_strategy.evaluate_entry(indicators)
            # Evaluate exit
            should_sell, exit_triggers = self.rule_strategy.evaluate_exit(indicators)

            signal_val = 0
            if should_buy and not should_sell:
                signal_val = 1
            elif should_sell:
                signal_val = -1

            stop_loss = None
            take_profit = None
            if signal_val != 0:
                # Simple ATR-based stops
                close = row['close']
                atr = row.get('atr', close * 0.02)
                if signal_val == 1:
                    stop_loss = close - (atr * 2)
                    take_profit = close * 1.05  # 5% target
                else:
                    stop_loss = close + (atr * 2)
                    take_profit = close * 0.95

            signals.append({
                'signal': signal_val,
                'confidence': confidence if signal_val == 1 else 0.9 if signal_val == -1 else 0.0,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
            })

        signals_df = pd.DataFrame(signals, index=data.index)
        return signals_df


def load_rule_strategy(rules_config_path: str) -> RuleStrategyBacktest:
    """Helper to load RuleStrategy from YAML file"""
    import yaml
    with open(rules_config_path, 'r') as f:
        config = yaml.safe_load(f)
        rules = config.get('rules', [])
    return RuleStrategyBacktest(rules)
