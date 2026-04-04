#!/usr/bin/env python3
"""
Stop‑Loss/Take‑Profit Strategy Comparison Study
Compare multiple exit frameworks on the same sma20_trend entry signals.
"""
import json
import pandas as pd
import numpy as np
from pathlib import Path
import yfinance as yf
from typing import Dict

# Universe (same as previous backtests)
UNIVERSE = [
    "NVDA", "PLTR", "TSM", "CRWD", "MSFT", "AAPL", "GOOGL", "AMZN",
    "META", "NFLX", "ADBE", "ASML", "AVGO", "CSCO", "INTU", "QCOM",
    "TMUS", "VRTX", "LQDA", "MSTR"
]

# Config
START_DATE = "2023-01-01"
END_DATE = "2024-12-31"

def compute_sma20(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure lowercase column names and compute SMA20."""
    df = df.copy()
    # Map common yFinance column names to lowercase standardized
    col_map = {
        'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close',
        'Adj Close': 'adj_close', 'Volume': 'volume'
    }
    df.rename(columns=lambda c: col_map.get(c, c.lower()), inplace=True)
    # If 'close' missing but 'adj_close' present, use adj_close
    if 'close' not in df.columns and 'adj_close' in df.columns:
        df['close'] = df['adj_close']
    df['sma20'] = df['close'].rolling(20).mean()
    return df

def simulate_fixed_pct(entry_price: float, future_df: pd.DataFrame, sl_pct=0.015, tp_pct=0.03) -> Dict:
    stop_price = entry_price * (1 - sl_pct)
    take_price = entry_price * (1 + tp_pct)
    exit_idx = None
    exit_reason = None
    for i, (_, row) in enumerate(future_df.iterrows()):
        if row['low'] <= stop_price:
            exit_idx = i
            exit_reason = "stop"
            break
        if row['high'] >= take_price:
            exit_idx = i
            exit_reason = "take"
            break
    if exit_idx is not None:
        exit_price = stop_price if exit_reason=="stop" else take_price
        pnl_pct = (exit_price - entry_price) / entry_price
        return {
            'exit_price': float(exit_price),
            'exit_day': int(exit_idx+1),
            'reason': exit_reason,
            'pnl_pct': float(pnl_pct)
        }
    else:
        last_price = future_df['close'].iloc[-1]
        return {
            'exit_price': float(last_price),
            'exit_day': len(future_df),
            'reason': 'end',
            'pnl_pct': float((last_price - entry_price)/entry_price)
        }

def simulate_atr(entry_price: float, hist_df: pd.DataFrame, future_df: pd.DataFrame,
                atr_mult_sl=2.0, atr_mult_tp=4.0) -> Dict:
    high = hist_df['high']
    low = hist_df['low']
    close = hist_df['close']
    tr = pd.DataFrame()
    tr['h-l'] = high - low
    tr['h-pc'] = abs(high - close.shift(1))
    tr['l-pc'] = abs(low - close.shift(1))
    atr_series = tr.max(axis=1).rolling(14).mean()
    atr = atr_series.iloc[-1]
    if pd.isna(atr) or atr <= 0:
        return None
    stop_price = entry_price - atr_mult_sl * atr
    take_price = entry_price + atr_mult_tp * atr
    exit_idx = None
    exit_reason = None
    for i, (_, row) in enumerate(future_df.iterrows()):
        if row['low'] <= stop_price:
            exit_idx = i
            exit_reason = "stop"
            break
        if row['high'] >= take_price:
            exit_idx = i
            exit_reason = "take"
            break
    if exit_idx is not None:
        exit_price = stop_price if exit_reason=="stop" else take_price
        pnl_pct = (exit_price - entry_price) / entry_price
        return {
            'exit_price': float(exit_price),
            'exit_day': int(exit_idx+1),
            'reason': exit_reason,
            'pnl_pct': float(pnl_pct)
        }
    else:
        last_price = future_df['close'].iloc[-1]
        return {
            'exit_price': float(last_price),
            'exit_day': len(future_df),
            'reason': 'end',
            'pnl_pct': float((last_price - entry_price)/entry_price)
        }

def simulate_partial_trail(entry_price: float, hist_df: pd.DataFrame, future_df: pd.DataFrame,
                          partial_pct=0.02, trail_atr_mult=1.5) -> Dict:
    partial_target = entry_price * (1 + partial_pct)
    high = hist_df['high']
    low = hist_df['low']
    close = hist_df['close']
    tr = pd.DataFrame()
    tr['h-l'] = high - low
    tr['h-pc'] = abs(high - close.shift(1))
    tr['l-pc'] = abs(low - close.shift(1))
    atr_series = tr.max(axis=1).rolling(14).mean()
    atr = atr_series.iloc[-1]
    if pd.isna(atr) or atr <= 0:
        return None
    trail_stop = entry_price - trail_atr_mult * atr
    # Find partial target day
    partial_day = None
    for i, (_, row) in enumerate(future_df.iterrows()):
        if row['high'] >= partial_target:
            partial_day = i + 1
            break
    # Find remainder exit
    exit_price_rem = None
    exit_reason_rem = None
    for i, (_, row) in enumerate(future_df.iterrows()):
        if row['low'] <= trail_stop:
            exit_price_rem = trail_stop
            exit_reason_rem = "trail_stop"
            break
    if exit_price_rem is None:
        exit_price_rem = future_df['close'].iloc[-1]
        exit_reason_rem = "end"
    pnl_partial = (partial_target - entry_price) / entry_price
    pnl_rem = (exit_price_rem - entry_price) / entry_price
    blended_pnl = 0.5 * pnl_partial + 0.5 * pnl_rem
    exit_day = partial_day if partial_day is not None else len(future_df)
    return {
        'exit_price': float(exit_price_rem),
        'exit_day': int(exit_day),
        'reason': f"partial_{exit_reason_rem}",
        'pnl_pct': float(blended_pnl)
    }

def run_study():
    all_results = []
    for symbol in UNIVERSE:
        try:
            df = yf.download(symbol, start=START_DATE, end=END_DATE, progress=False)
            if df.empty:
                print(f"No data for {symbol}")
                continue
            df = compute_sma20(df)
            # Need at least 20 days for SMA
            if len(df) < 30:
                continue
            # Entry signals: price crosses above SMA20 from below
            df['prev_close'] = df['close'].shift(1)
            df['prev_sma20'] = df['sma20'].shift(1)
            df['signal'] = (df['close'] > df['sma20']) & (df['prev_close'] <= df['prev_sma20'])
            entry_dates = df.index[df['signal']].tolist()
            print(f"{symbol}: {len(entry_dates)} entry signals")
            for entry_date in entry_dates:
                entry_idx = df.index.get_loc(entry_date)
                # Need enough history for ATR (14 periods) plus SMA buffer
                if entry_idx < 20:
                    continue
                entry_price = df['close'].iloc[entry_idx]
                # future data for exit simulation
                future = df.iloc[entry_idx+1:]
                if future.empty:
                    continue
                # 1. Fixed pct
                res_fixed = simulate_fixed_pct(entry_price, future)
                res_fixed['strategy'] = 'fixed_pct'
                res_fixed['symbol'] = symbol
                res_fixed['entry_date'] = entry_date.strftime('%Y-%m-%d')
                all_results.append(res_fixed)
                # 2. ATR
                hist = df.iloc[:entry_idx+1]
                res_atr = simulate_atr(entry_price, hist, future)
                if res_atr:
                    res_atr['strategy'] = 'atr'
                    res_atr['symbol'] = symbol
                    res_atr['entry_date'] = entry_date.strftime('%Y-%m-%d')
                    all_results.append(res_atr)
                # 3. Partial trail
                res_partial = simulate_partial_trail(entry_price, hist, future)
                if res_partial:
                    res_partial['strategy'] = 'partial_trail'
                    res_partial['symbol'] = symbol
                    res_partial['entry_date'] = entry_date.strftime('%Y-%m-%d')
                    all_results.append(res_partial)
        except Exception as e:
            print(f"Error processing {symbol}: {e}")
            continue

    # Save raw results
    Path('studies').mkdir(exist_ok=True)
    raw_path = Path('studies/stop_loss_comparison_raw.json')
    with open(raw_path, 'w') as f:
        json.dump(all_results, f, indent=2)

    if not all_results:
        print("No results to summarize.")
        return
    # Summary DataFrame
    df_res = pd.DataFrame(all_results)
    summary = df_res.groupby('strategy')['pnl_pct'].agg(['mean','std','count','sum','min','max'])
    summary['win_rate'] = df_res.groupby('strategy')['pnl_pct'].apply(lambda x: (x>0).mean())
    summary['avg_holding_days'] = df_res.groupby('strategy')['exit_day'].mean()
    summary = summary.round(4)
    summary_path = Path('studies/stop_loss_comparison_summary.csv')
    summary.to_csv(summary_path)
    print("Study complete. Raw:", raw_path, "Summary:", summary_path)
    print(summary)

if __name__ == "__main__":
    run_study()
