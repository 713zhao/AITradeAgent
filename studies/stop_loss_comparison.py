#!/usr/bin/env python3
import json
import pandas as pd
import numpy as np
from pathlib import Path
import yfinance as yf

UNIVERSE = ["NVDA","PLTR","TSM","CRWD","MSFT","AAPL","GOOGL","AMZN","META","NFLX","ADBE","ASML","AVGO","CSCO","INTU","QCOM","TMUS","VRTX","LQDA","MSTR"]
START_DATE = "2023-01-01"
END_DATE = "2024-12-31"

def compute_arrays(df):
    # yFinance may return MultiIndex columns; flatten to single-level
    if isinstance(df.columns, pd.MultiIndex):
        # Keep only first level ('Close', 'High', etc.) and drop second (ticker)
        df.columns = df.columns.get_level_values(0)
    # Extract 1D arrays; use .squeeze() to remove any extra dimensions
    close = df['Close'].to_numpy(dtype=float).squeeze()
    high = df['High'].to_numpy(dtype=float).squeeze()
    low = df['Low'].to_numpy(dtype=float).squeeze()
    # Compute SMA20 using numpy
    sma20 = np.full_like(close, np.nan, dtype=float)
    if len(close) >= 20:
        cumsum = np.cumsum(np.insert(close, 0, 0.0))
        sma20[19:] = (cumsum[20:] - cumsum[:-20]) / 20.0
    return close, high, low, sma20

def atr_array(high, low, close, period=14):
    n = len(high)
    tr = np.zeros(n)
    for i in range(n):
        if i == 0:
            tr[i] = high[i] - low[i]
        else:
            tr[i] = max(high[i] - low[i], abs(high[i] - close[i-1]), abs(low[i] - close[i-1]))
    atr = np.convolve(tr, np.ones(period)/period, mode='same')
    atr[:period-1] = np.nan
    return atr

def simulate_fixed_pct(entry_price, future_high, future_low, sl_pct=0.015, tp_pct=0.03):
    stop_price = entry_price * (1 - sl_pct)
    take_price = entry_price * (1 + tp_pct)
    for i in range(len(future_high)):
        if future_low[i] <= stop_price:
            exit_price = stop_price
            pnl = (exit_price - entry_price) / entry_price
            return {'exit_price': float(exit_price), 'exit_day': i+1, 'reason': 'stop', 'pnl_pct': float(pnl)}
        if future_high[i] >= take_price:
            exit_price = take_price
            pnl = (exit_price - entry_price) / entry_price
            return {'exit_price': float(exit_price), 'exit_day': i+1, 'reason': 'take', 'pnl_pct': float(pnl)}
    # no exit
    last_price = future_high[-1]
    pnl = (last_price - entry_price) / entry_price
    return {'exit_price': float(last_price), 'exit_day': len(future_high), 'reason': 'end', 'pnl_pct': float(pnl)}

def simulate_atr(entry_price, entry_idx, high, low, close, atr, future_indices, mult_sl=2.0, mult_tp=4.0):
    if entry_idx < 14 or np.isnan(atr[entry_idx]):
        return None
    stop_price = entry_price - mult_sl * atr[entry_idx]
    take_price = entry_price + mult_tp * atr[entry_idx]
    for offset, i in enumerate(future_indices):
        if low[i] <= stop_price:
            pnl = (stop_price - entry_price) / entry_price
            return {'exit_price': float(stop_price), 'exit_day': offset+1, 'reason': 'stop', 'pnl_pct': float(pnl)}
        if high[i] >= take_price:
            pnl = (take_price - entry_price) / entry_price
            return {'exit_price': float(take_price), 'exit_day': offset+1, 'reason': 'take', 'pnl_pct': float(pnl)}
    last_price = close[future_indices[-1]]
    pnl = (last_price - entry_price) / entry_price
    return {'exit_price': float(last_price), 'exit_day': len(future_indices), 'reason': 'end', 'pnl_pct': float(pnl)}

def simulate_partial(entry_price, entry_idx, high, low, close, atr, future_indices, partial_pct=0.02, trail_mult=1.5):
    if entry_idx < 14 or np.isnan(atr[entry_idx]):
        return None
    target = entry_price * (1 + partial_pct)
    trail_stop = entry_price - trail_mult * atr[entry_idx]
    partial_day = None
    for offset, i in enumerate(future_indices):
        if high[i] >= target:
            partial_day = offset + 1
            break
    exit_price_rem = None
    exit_reason = None
    for offset, i in enumerate(future_indices):
        if low[i] <= trail_stop:
            exit_price_rem = trail_stop
            exit_reason = 'trail_stop'
            break
    if exit_price_rem is None:
        exit_price_rem = close[future_indices[-1]]
        exit_reason = 'end'
    pnl_partial = (target - entry_price) / entry_price
    pnl_rem = (exit_price_rem - entry_price) / entry_price
    blended = 0.5 * pnl_partial + 0.5 * pnl_rem
    exit_day = partial_day if partial_day is not None else len(future_indices)
    return {'exit_price': float(exit_price_rem), 'exit_day': int(exit_day), 'reason': f"partial_{exit_reason}", 'pnl_pct': float(blended)}

def run():
    results = []
    for symbol in UNIVERSE:
        try:
            df = yf.download(symbol, start=START_DATE, end=END_DATE, progress=False)
            if df.empty:
                print(f"No data for {symbol}")
                continue
            close, high, low, sma20 = compute_arrays(df)
            n = len(close)
            if n < 30:
                continue
            # signals: close > sma20 and previous close <= previous sma20
            prev_close = np.roll(close, 1)
            prev_sma = np.roll(sma20, 1)
            signal = (close > sma20) & (prev_close <= prev_sma)
            signal[0] = False
            entry_idxs = np.where(signal)[0]
            print(f"{symbol}: {len(entry_idxs)} entries")
            atr = atr_array(high, low, close, period=14)
            for entry_idx in entry_idxs:
                if entry_idx < 20:
                    continue
                entry_price = close[entry_idx]
                future = np.arange(entry_idx+1, n)
                if len(future) == 0:
                    continue
                # Fixed pct
                r1 = simulate_fixed_pct(entry_price, high[future], low[future])
                r1.update(strategy='fixed_pct', symbol=symbol, entry_date=str(df.index[entry_idx].date()))
                results.append(r1)
                # ATR
                r2 = simulate_atr(entry_price, entry_idx, high, low, close, atr, future)
                if r2:
                    r2.update(strategy='atr', symbol=symbol, entry_date=str(df.index[entry_idx].date()))
                    results.append(r2)
                # Partial trail
                r3 = simulate_partial(entry_price, entry_idx, high, low, close, atr, future)
                if r3:
                    r3.update(strategy='partial_trail', symbol=symbol, entry_date=str(df.index[entry_idx].date()))
                    results.append(r3)
        except Exception as e:
            import traceback; traceback.print_exc()
            continue

    Path('studies').mkdir(exist_ok=True)
    with open('studies/stop_loss_raw.json', 'w') as f:
        json.dump(results, f, indent=2)
    if not results:
        print("No results.")
        return
    df_res = pd.DataFrame(results)
    summary = df_res.groupby('strategy')['pnl_pct'].agg(['mean','std','count','sum','min','max'])
    summary['win_rate'] = df_res.groupby('strategy')['pnl_pct'].apply(lambda x: (x>0).mean())
    summary['avg_holding_days'] = df_res.groupby('strategy')['exit_day'].mean()
    summary = summary.round(4)
    summary.to_csv('studies/stop_loss_summary.csv')
    print("Study complete. Summary:")
    print(summary)

if __name__ == "__main__":
    run()
