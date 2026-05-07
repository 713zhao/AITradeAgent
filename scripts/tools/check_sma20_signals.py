#!/usr/bin/env python3
"""Diagnostic: Check current SMA20 signals across universe"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
from finance_service.core.config import YAMLConfigEngine
from finance_service.data.provider_factory import DataProviderFactory
from finance_service.indicators.indicators import calculate_sma

async def check_universe():
    config_engine = YAMLConfigEngine("config/finance.yaml")
    factory = DataProviderFactory(config_engine)
    provider = factory.get_provider()
    universe = config_engine.get("finance", "universe/all_symbols", default=[])
    print(f"Checking {len(universe)} symbols...")
    results = []
    for symbol in universe:
        try:
            df = await provider.fetch_data(symbol, interval="1h", lookback_days=30)
            if df is None or len(df) < 20:
                print(f"  {symbol}: insufficient data ({len(df) if df is not None else 0} points)")
                continue
            latest = df.iloc[-1]
            close = latest['close']
            sma20 = df['close'].tail(20).mean()
            signal = close > sma20
            results.append({
                'symbol': symbol,
                'close': round(close, 2),
                'sma20': round(sma20, 2),
                'above': signal,
                'diff_pct': round((close - sma20) / sma20 * 100, 1)
            })
        except Exception as e:
            print(f"  {symbol}: error - {e}")
            results.append({'symbol': symbol, 'error': str(e)})
    
    # Summary
    above_count = sum(1 for r in results if r.get('above'))
    print(f"\n=== SMA20 Trend Signals ===")
    print(f"Total symbols: {len(results)}")
    print(f"Above SMA20 (BUY signals): {above_count}")
    print(f"Below SMA20 (NO signal): {len(results) - above_count}")
    
    # Show top gainers relative to SMA20
    if results:
        valid = [r for r in results if 'above' in r]
        sorted_by_diff = sorted(valid, key=lambda x: x['diff_pct'], reverse=True)[:10]
        print("\nTop 10 above SMA20 (% diff):")
        for r in sorted_by_diff:
            print(f"  {r['symbol']}: ${r['close']} vs SMA20 ${r['sma20']} (+{r['diff_pct']}%)")
    
    return results

if __name__ == "__main__":
    asyncio.run(check_universe())
