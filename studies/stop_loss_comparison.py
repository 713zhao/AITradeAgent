#!/usr/bin/env python3
"""
Stop‑Loss/Take‑Profit Strategy Comparison Study
Compare multiple exit frameworks on the same sma20_trend entry signals.
Uses numpy arrays to avoid pandas alignment issues.
"""
import json
import pandas as pd
import numpy as np
from pathlib import Path
import yfinance as yf

UNIVERSE = [
    "NVDA", "PLTR", "TSM", "CRWD", "MSFT", "AAPL", "GOOGL", "AMZN",
    "META", "NFLX", "ADBE", "ASML", "AVGO", "CSCO", "INTU", "QCOM",
    "TMUS", "VRTX", "LQDA", "MSTR"
]
START_DATE = "2023-01-01"
END_DATE = "2024-12-31"

def compute_indicators(df: pd.DataFrame):
    """Return numpy arrays: close, high, low, sma20."""
    # Use lowercase mapping
    df = df.copy()
    col_map = {'Open':'open','High':'high','Low':'low','Close':'close','Adj Close':'adj_close','Volume':'volume'}
    df.rename(columns=lambda c: col_map.get(c, c.lower()), inplace=True)
    if 'close' not in df.columns and 'adj_close' in df.columns:
        df['close'] = df['adj_close']
    close = df['close'].to_numpy(dtype=float)
    high = df['high'].to_numpy(dtype=float)
    low = df['low'].to_numpy(dtype=float)
    # SMA20
    sma20 = pd.Series(close).rolling(20).mean().to_numpy()
    return close, high, low, sma20

def atr_from_arrays(high, low, close, period=14):
    """Compute ATR as numpy array."""
    n = len(high)
    tr = np.zeros(n)
    for i in range(n):
        if i == 0:
            tr[i] = high[i] - low[i]
        else:
            tr[i] = max(high[i] - low[i], abs(high[i] - close[i-1]), abs(low[i] - close[i-1]))
    atr = np.convolve(tr, np.ones(period)/period, mode='valid')
    # pad with nan to same length
    pad = np.full(period-1, np.nan)
    atr = np.concatenate([pad, atr])
    return atr

def simulate_fixed_pct(entry_price, future_high, future_low, sl_pct=0.015, tp_pct=0.03):
    stop_price = entry_price * (1 - sl_pct)
    take_price = entry_price * (1 + tp_pct)
    exit_idx = None
    exit_reason = None
    for i in range(len(future_high)):
        if future_low[i] <= stop_price:
            exit_idx = i
            exit_reason = "stop"
            break
        if future_high[i] >= take_price:
            exit_idx = i
            exit_reason = "take"
            break
    if exit_idx is not None:
        exit_price = stop_price if exit_reason=="stop" else take_price
        pnl_pct = (exit_price - entry_price) / entry_price
        return {'exit_price': float(exit_price), 'exit_day': int(exit_idx+1), 'reason': exit_reason, 'pnl_pct': float(pnl_pct)}
    else:
        last_price = future_high[-1]  # close approximates
        return {'exit_price': float(last_price), 'exit_day': len(future_high), 'reason': 'end', 'pnl_pct': float((last_price - entry_price)/entry_price)}

def simulate_atr(entry_price, entry_idx, high, low, close, atr, future_indices, atr_mult_sl=2.0, atr_mult_tp=4.0):
    if entry_idx < 14 or np.isnan(atr[entry_idx]):
        return None
    stop_price = entry_price - atr_mult_sl * atr[entry_idx]
    take_price = entry_price + atr_mult_tp * atr[entry_idx]
    exit_idx = None
    exit_reason = None
    for offset, i in enumerate(future_indices):
        if low[i] <= stop_price:
            exit_idx = offset
            exit_reason = "stop"
            break
        if high[i] >= take_price:
            exit_idx = offset
            exit_reason = "take"
            break
    if exit_idx is not None:
        exit_price = stop_price if exit_reason=="stop" else take_price
        pnl_pct = (exit_price - entry_price) / entry_price
        return {'exit_price': float(exit_price), 'exit_day': int(exit_idx+1), 'reason': exit_reason, 'pnl_pct': float(pnl_pct)}
    else:
        last_price = close[future_indices[-1]]
        return {'exit_price': float(last_price), 'exit_day': len(future_indices), 'reason': 'end', 'pnl_pct': float((last_price - entry_price)/entry_price)}

def simulate_partial_trail(entry_price, entry_idx, high, low, close, atr, future_indices, partial_pct=0.02, trail_atr_mult=1.5):
    if entry_idx < 14 or np.isnan(atr[entry_idx]):
        return None
    partial_target = entry_price * (1 + partial_pct)
    trail_stop = entry_price - trail_atr_mult * atr[entry_idx]
    # Find partial target day
    partial_day = None
    for offset, i in enumerate(future_indices):
        if high[i] >= partial_target:
            partial_day = offset + 1
            break
    # Find remainder exit
    exit_price_rem = None
    exit_reason_rem = None
    for offset, i in enumerate(future_indices):
        if low[i] <= trail_stop:
            exit_price_rem = trail_stop
            exit_reason_rem = "trail_stop"
            break
    if exit_price_rem is None:
        exit_price_rem = close[future_indices[-1]]
        exit_reason_rem = "end"
    pnl_partial = (partial_target - entry_price) / entry_price
    pnl_rem = (exit_price_rem - entry_price) / entry_price
    blended_pnl = 0.5 * pnl_partial + 0.5 * pnl_rem
    exit_day = partial_day if partial_day is not None else len(future_indices)
    return {'exit_price': float(exit_price_rem), 'exit_day': int(exit_day), 'reason': f"partial_{exit_reason_rem}", 'pnl_pct': float(blended_pnl)}

def run_study():
    all_results = []
    for symbol in UNIVERSE:
        try:
            df = yf.download(symbol, start=START_DATE, end=END_DATE, progress=False)
            if df.empty:
                print(f"No data for {symbol}")
                continue
            close, high, low, sma20 = compute_indicators(df)
            n = len(close)
            if n < 30:
                continue
            # Entry signals: close > sma20 and previous close <= previous sma20
            signal = (close > sma20) & (np.roll(close, 1) <= np.roll(sma20, 1))
            # skip first element due to roll
            signal[0] = False
            entry_indices = np.where(signal)[0]
            print(f"{symbol}: {len(entry_indices)} entry signals")
            # Precompute ATR array
            atr = atr_from_arrays(high, low, close, period=14)
            for entry_idx in entry_indices:
                if entry_idx < 20:
                    continue
                entry_price = close[entry_idx]
                # future indices from entry_idx+1 to end
                future_idxs = np.arange(entry_idx+1, n)
                if len(future_idxs) == 0:
                    continue
                # 1. Fixed pct
                res_fixed = simulate_fixed_pct(entry_price, high[future_idxs], low[future_idxs])
                res_fixed['strategy'] = 'fixed_pct'
                res_fixed['symbol'] = symbol
                res_fixed['entry_date'] = str(df.index[entry_idx].date())
                all_results.append(res_fixed)
                # 2. ATR
                res_atr = simulate_atr(entry_price, entry_idx, high, low, close, atr, future_idxs)
                if res_atr:
                    res_atr['strategy'] = 'atr'
                    res_atr['symbol'] = symbol
                    res_atr['entry_date'] = str(df.index[entry_idx].date())
                    all_results.append(res_atr)
                # 3. Partial trail
                res_partial = simulate_partial_trail(entry_price, entry_idx, high, low, close, atr, future_idxs)
                if res_partial:
                    res_partial['strategy'] = 'partial_trail'
                    res_partial['symbol'] = symbol
                    res_partial['entry_date'] = str(df.index[entry_idx].date())
                    all_results.append(res_partial)
        except Exception as e:
            import traceback
            print(f"Error processing {symbol}: {e}")
            traceback.print_exc()
            continue

    Path('studies').mkdir(exist_ok=True)
    raw_path = Path('studies/stop_loss_comparison_raw.json')
    with open(raw_path, 'w') as f:
        json.dump(all_results, f, indent=2)

    if not all_results:
        print("No results.")
        return
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
