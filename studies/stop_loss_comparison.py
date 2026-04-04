#!/usr/bin/env python3
"""
Stop‑Loss/Take‑Profit Strategy Comparison Study
Compare multiple exit frameworks on the same sma20_trend entry signals.
"""
import json
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import yfinance as yf
from typing import Dict, List, Tuple

# Universe (same as previous backtests)
UNIVERSE = [
    "NVDA", "PLTR", "TSM", "CRWD", "MSFT", "AAPL", "GOOGL", "AMZN",
    "META", "NFLX", "ADBE", "ASML", "AVGO", "CSCO", "INTU", "QCOM",
    "TMUS", "VRTX", "LQDA", "MSTR"
]

# Config
START_DATE = "2023-01-01"
END_DATE = "2024-12-31"
INITIAL_CAPITAL = 100_000
COMMISSION = 0.001  # 0.1% per trade

# SMA20 trend entry
def compute_sma20(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df['sma20'] = df['close'].rolling(20).mean()
    return df

# Strategies
def fixed_pct_exit(entry_price: float, direction: str, sl_pct=0.015, tp_pct=0.03) -> Tuple[float, str]:
    """Return (exit_price, reason) for fixed percent stop/take."""
    if direction == "BUY":
        stop = entry_price * (1 - sl_pct)
        take = entry_price * (1 + tp_pct)
        return (stop, take)
    else:  # SELL/short not supported
        return (None, None)

def atr_exit(entry_price: float, df: pd.DataFrame, atr_mult_sl=2.0, atr_mult_tp=4.0) -> Tuple[float, float]:
    """Use ATR(14) for stop/take levels."""
    high = df['high']
    low = df['low']
    close = df['close']
    # compute ATR
    tr = pd.DataFrame()
    tr['h-l'] = high - low
    tr['h-pc'] = abs(high - close.shift(1))
    tr['l-pc'] = abs(low - close.shift(1))
    atr = tr.max(axis=1).rolling(14).mean()
    latest_atr = atr.iloc[-1]
    stop = entry_price - atr_mult_sl * latest_atr
    take = entry_price + atr_mult_tp * latest_atr
    return (stop, take)

def partial_trail_exit(entry_price: float, df: pd.DataFrame, partial_pct=0.02, trail_atr_mult=1.5) -> Tuple[float, float, float]:
    """Return (partial_target, trail_stop, remainder_holds)."""
    partial_target = entry_price * (1 + partial_pct)
    # Trail stop based on ATR
    high = df['high']
    low = df['low']
    close = df['close']
    tr = pd.DataFrame()
    tr['h-l'] = high - low
    tr['h-pc'] = abs(high - close.shift(1))
    tr['l-pc'] = abs(low - close.shift(1))
    atr = tr.max(axis=1).rolling(14).mean()
    latest_atr = atr.iloc[-1]
    trail_stop = entry_price - trail_atr_mult * latest_atr
    return (partial_target, trail_stop, None)  # remainder_holds not needed here

def simulate_exits(df: pd.DataFrame, entry_idx: int, direction: str = "BUY") -> Dict[str, any]:
    """Simulate various exit strategies from entry at entry_idx."""
    entry_price = df['close'].iloc[entry_idx]
    exit_metrics = {}
    # Forward window for evaluation
    future = df.iloc[entry_idx+1:]
    if future.empty:
        return exit_metrics
    
    # 1. Fixed pct
    stop_fixed = entry_price * 0.985
    take_fixed = entry_price * 1.03
    # find first event
    exit_idx = None
    exit_reason = None
    for i, (idx, row) in enumerate(future.iterrows()):
        if row['low'] <= stop_fixed:
            exit_idx = i
            exit_reason = "stop"
            break
        if row['high'] >= take_fixed:
            exit_idx = i
            exit_reason = "take"
            break
    if exit_idx is not None:
        exit_price = stop_fixed if exit_reason=="stop" else take_fixed
        holding_days = exit_idx + 1
        pnl_pct = (exit_price - entry_price) / entry_price
        exit_metrics['fixed_pct'] = {
            'exit_price': float(exit_price),
            'exit_day': int(exit_idx+1),
            'reason': exit_reason,
            'pnl_pct': float(pnl_pct)
        }
    else:
        # hold until end
        last_price = future['close'].iloc[-1]
        exit_metrics['fixed_pct'] = {
            'exit_price': float(last_price),
            'exit_day': len(future),
            'reason': 'end',
            'pnl_pct': float((last_price - entry_price)/entry_price)
        }
    
    # 2. ATR-based
    # compute ATR using data up to entry (excluding future)
    hist = df.iloc[:entry_idx+1]
    if len(hist) >= 14:
        high = hist['high']
        low = hist['low']
        close = hist['close']
        tr = pd.DataFrame()
        tr['h-l'] = high - low
        tr['h-pc'] = abs(high - close.shift(1))
        tr['l-pc'] = abs(low - close.shift(1))
        atr_series = tr.max(axis=1).rolling(14).mean()
        atr = atr_series.iloc[-1]
        stop_atr = entry_price - 2 * atr
        take_atr = entry_price + 4 * atr
        exit_idx2 = None
        exit_reason2 = None
        for i, (idx, row) in enumerate(future.iterrows()):
            if row['low'] <= stop_atr:
                exit_idx2 = i
                exit_reason2 = "stop"
                break
            if row['high'] >= take_atr:
                exit_idx2 = i
                exit_reason2 = "take"
                break
        if exit_idx2 is not None:
            exit_price2 = stop_atr if exit_reason2=="stop" else take_atr
            pnl_pct2 = (exit_price2 - entry_price) / entry_price
            exit_metrics['atr'] = {
                'exit_price': float(exit_price2),
                'exit_day': int(exit_idx2+1),
                'reason': exit_reason2,
                'pnl_pct': float(pnl_pct2)
            }
        else:
            last_price = future['close'].iloc[-1]
            exit_metrics['atr'] = {
                'exit_price': float(last_price),
                'exit_day': len(future),
                'reason': 'end',
                'pnl_pct': float((last_price - entry_price)/entry_price)
            }
    else:
        exit_metrics['atr'] = None  # not enough data
    
    # 3. RSI overbought exit (add later)
    # For now return basic
    return exit_metrics

# Main: iterate universe, find entry signals, simulate exits, aggregate
def run_study():
    results = []
    for symbol in UNIVERSE:
        try:
            df = yf.download(symbol, start=START_DATE, end=END_DATE, progress=False)
            if df.empty:
                continue
            df = compute_sma20(df)
            # Entry: when close crosses above SMA20 (from below)
            df['prev_close'] = df['Close'].shift(1)
            df['prev_sma20'] = df['sma20'].shift(1)
            df['signal'] = (df['Close'] > df['sma20']) & (df['prev_close'] <= df['prev_sma20'])
            # Also allow holding while still above SMA20, but we only enter on first cross after being below
            # We'll take all signals as entry dates; in reality you would avoid overlapping
            entry_dates = df.index[df['signal']].tolist()
            for entry_date in entry_dates:
                entry_idx = df.index.get_loc(entry_date)
                # Ensure enough lookback for indicators
                if entry_idx < 20:
                    continue
                # Simulate exits
                sim = simulate_exits(df, entry_idx, direction="BUY")
                for strategy, outcome in sim.items():
                    if outcome is None:
                        continue
                    results.append({
                        'symbol': symbol,
                        'entry_date': entry_date.strftime('%Y-%m-%d'),
                        'strategy': strategy,
                        'exit_price': outcome['exit_price'],
                        'holding_days': outcome['exit_day'],
                        'exit_reason': outcome['reason'],
                        'pnl_pct': outcome['pnl_pct']
                    })
        except Exception as e:
            print(f"Error processing {symbol}: {e}")
            continue
    
    # Save raw results
    Path('studies').mkdir(exist_ok=True)
    raw_path = Path('studies/stop_loss_comparison_raw.json')
    with open(raw_path, 'w') as f:
        json.dump(results, f, indent=2)
    
    # Compare aggregated stats
    df_res = pd.DataFrame(results)
    summary = df_res.groupby('strategy')['pnl_pct'].agg(['mean','std','count','sum','min','max'])
    summary['win_rate'] = df_res.groupby('strategy')['pnl_pct'].apply(lambda x: (x>0).mean())
    summary['avg_win'] = df_res[df_res['pnl_pct']>0].groupby('strategy')['pnl_pct'].mean()
    summary['avg_loss'] = df_res[df_res['pnl_pct']<0].groupby('strategy')['pnl_pct'].mean()
    summary = summary.round(4)
    summary_path = Path('studies/stop_loss_comparison_summary.csv')
    summary.to_csv(summary_path)
    print("Study complete. Raw:", raw_path, "Summary:", summary_path)
    print(summary)

if __name__ == "__main__":
    run_study()
