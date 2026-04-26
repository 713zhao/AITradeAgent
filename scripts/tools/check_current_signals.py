#!/usr/bin/env python3
"""Check SMA20 signals for the top 10 symbols from universe"""
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

# Top 10 symbols as determined by alphabetical order (including HK)
symbols = [
    "0388.HK", "0700.HK", "0941.HK", "1398.HK", "9988.HK",
    "AAPL", "AMD", "AMZN", "ASML", "ASR"
]

print(f"Checking {len(symbols)} symbols...")
end_date = datetime.now()
start_date = end_date - timedelta(days=60)  # need at least 20 days

results = []
for symbol in symbols:
    try:
        ticker = yf.Ticker(symbol)
        # Use daily data, adjust for HK vs US
        hist = ticker.history(start=start_date, end=end_date, interval="1d")
        if hist.empty:
            print(f"{symbol}: no data")
            continue
        closes = hist['Close']
        if len(closes) < 20:
            print(f"{symbol}: insufficient data ({len(closes)} days)")
            continue
        latest_close = closes.iloc[-1]
        sma20 = closes.tail(20).mean()
        above = latest_close > sma20
        results.append({
            'symbol': symbol,
            'close': round(latest_close, 2),
            'sma20': round(sma20, 2),
            'above': above,
            'diff_pct': round((latest_close - sma20) / sma20 * 100, 1)
        })
    except Exception as e:
        print(f"{symbol}: error - {e}")

above_count = sum(1 for r in results if r['above'])
print(f"\n=== SMA20 Signals ===")
print(f"Total: {len(results)}, Above (BUY): {above_count}, Below: {len(results)-above_count}")
print("\nTop gainers vs SMA20:")
for r in sorted(results, key=lambda x: x['diff_pct'], reverse=True)[:5]:
    print(f"  {r['symbol']}: ${r['close']} vs SMA20 ${r['sma20']} (+{r['diff_pct']}%)")

if above_count == 0:
    print("\n⚠️  No symbols above SMA20! Market may be in downtrend. Strategy won't generate trades.")
else:
    print(f"\n✅ {above_count} symbols have buy signals.")
