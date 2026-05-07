"""Exit Strategy Skill – reusable exit logic for backtests and live trading."""
import numpy as np
from dataclasses import dataclass
from typing import Optional, Dict, Any, List

@dataclass
class ExitResult:
    strategy: str
    exit_price: float
    exit_day: int  # days after entry (1 = next day)
    reason: str
    pnl_pct: float
    metadata: Optional[Dict[str, Any]] = None

class ExitStrategy:
    """Collection of exit simulation methods."""

    @staticmethod
    def fixed_pct(entry_price: float, future_high: np.ndarray, future_low: np.ndarray,
                  sl_pct: float = 0.015, tp_pct: float = 0.03) -> ExitResult:
        stop_price = entry_price * (1 - sl_pct)
        take_price = entry_price * (1 + tp_pct)
        for i in range(len(future_high)):
            if future_low[i] <= stop_price:
                return ExitResult("fixed_pct", stop_price, i+1, "stop", (stop_price - entry_price) / entry_price)
            if future_high[i] >= take_price:
                return ExitResult("fixed_pct", take_price, i+1, "take", (take_price - entry_price) / entry_price)
        # No exit triggered
        last_price = future_high[-1]
        return ExitResult("fixed_pct", last_price, len(future_high), "end", (last_price - entry_price) / entry_price)

    @staticmethod
    def atr(entry_price: float, entry_idx: int, high: np.ndarray, low: np.ndarray, close: np.ndarray,
            atr: np.ndarray, future_indices: np.ndarray, mult_sl: float = 2.0, mult_tp: float = 4.0) -> Optional[ExitResult]:
        if entry_idx < 14 or np.isnan(atr[entry_idx]):
            return None
        stop_price = entry_price - mult_sl * atr[entry_idx]
        take_price = entry_price + mult_tp * atr[entry_idx]
        for offset, i in enumerate(future_indices):
            if low[i] <= stop_price:
                return ExitResult("atr", stop_price, offset+1, "stop", (stop_price - entry_price) / entry_price)
            if high[i] >= take_price:
                return ExitResult("atr", take_price, offset+1, "take", (take_price - entry_price) / entry_price)
        last_price = close[future_indices[-1]]
        return ExitResult("atr", last_price, len(future_indices), "end", (last_price - entry_price) / entry_price)

    @staticmethod
    def partial_trail(entry_price: float, entry_idx: int, high: np.ndarray, low: np.ndarray, close: np.ndarray,
                      atr: np.ndarray, future_indices: np.ndarray, partial_pct: float = 0.02,
                      trail_mult: float = 1.5) -> Optional[ExitResult]:
        """50% at partial target, remainder trails at trail_stop."""
        if entry_idx < 14 or np.isnan(atr[entry_idx]):
            return None
        target = entry_price * (1 + partial_pct)
        trail_stop = entry_price - trail_mult * atr[entry_idx]
        # Find partial target day
        partial_day = None
        for offset, i in enumerate(future_indices):
            if high[i] >= target:
                partial_day = offset + 1
                break
        # Find remainder exit price (first hit of trail_stop or final close)
        exit_price_rem = None
        exit_reason = None
        for offset, i in enumerate(future_indices):
            if low[i] <= trail_stop:
                exit_price_rem = trail_stop
                exit_reason = "trail_stop"
                break
        if exit_price_rem is None:
            exit_price_rem = close[future_indices[-1]]
            exit_reason = "end"
        # Blended P&L: 50% at target, 50% at remainder exit
        pnl_partial = (target - entry_price) / entry_price
        pnl_rem = (exit_price_rem - entry_price) / entry_price
        blended = 0.5 * pnl_partial + 0.5 * pnl_rem
        exit_day = partial_day if partial_day is not None else len(future_indices)
        return ExitResult("partial_trail", exit_price_rem, exit_day, f"partial_{exit_reason}", blended)

    @staticmethod
    def time_stop(entry_price: float, future_close: np.ndarray, max_days: int = 10) -> ExitResult:
        """Exit after max_days at closing price."""
        if len(future_close) < max_days:
            exit_price = future_close[-1]
            exit_day = len(future_close)
        else:
            exit_price = future_close[max_days-1]
            exit_day = max_days
        pnl = (exit_price - entry_price) / entry_price
        return ExitResult("time_stop", exit_price, exit_day, "time_exit", pnl)
