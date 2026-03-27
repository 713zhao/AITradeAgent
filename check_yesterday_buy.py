#!/usr/bin/env python3
"""
Check yesterday's data for ASML and ASR to see if buy conditions were met.
Strategy: sma20_trend (live trading strategy)
Condition: price > sma_20
Also shows ATR for position sizing.
"""

import sys
sys.path.insert(0, '.')

from finance_service.core.yaml_config import YAMLConfigEngine
from finance_service.agents.data_agent import DataAgent
from finance_service.agents.analysis_agent import AnalysisAgent
import pandas as pd
from datetime import datetime, timedelta

config = YAMLConfigEngine('config')
data_agent = DataAgent(config)
analysis_agent = AnalysisAgent()  # uses default periods

# Yesterday's date (US market)
# We need the most recent completed trading day. Assuming today is 2026-03-26, yesterday was 2026-03-25.
yesterday = '2026-03-25'
start_date = (datetime.strptime(yesterday, '%Y-%m-%d') - timedelta(days=400)).strftime('%Y-%m-%d')
end_date = yesterday

print(f"=== Checking BUY conditions for {yesterday} ===\n")

for symbol in ['ASML', 'ASR']:
    print(f"Fetching {symbol}...")
    # Use asyncio to run the async method
    import asyncio
    async def fetch_and_analyze():
        report = await data_agent.run(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            interval='1d',
            use_cache=False,
            emit_events=False
        )
        if report.status != 'success':
            print(f"  ERROR: {report.message}")
            return None
        df = pd.DataFrame.from_dict(report.payload['dataframe'])
        fundamentals = report.payload.get('fundamentals', {})
        # Ensure index is datetime and sorted
        if 'date' in df.columns:
            df.set_index('date', inplace=True)
        df.index = pd.to_datetime(df.index)
        df.sort_index(inplace=True)
        # Get the last row (yesterday)
        if df.empty:
            print(f"  ERROR: No data")
            return None
        last_row = df.iloc[-1]
        # Need enough history for indicators: use the whole df
        try:
            snapshot = analysis_agent._calculate_all(df, symbol, fundamentals=fundamentals)
            # snapshot is IndicatorsSnapshot; it has current_price and indicators dict
            # current_price should match last_row['close']
            price = snapshot.current_price
            sma20 = snapshot.indicators.get('sma_20')
            atr = snapshot.indicators.get('atr')
            regime = snapshot.indicators.get('regime_score')
            if sma20 is not None:
                sma20_val = sma20.value
                condition_met = price > sma20_val
            else:
                sma20_val = None
                condition_met = False
            print(f"  Close: {price:.2f}")
            print(f"  SMA20: {sma20_val:.2f}" if sma20_val else "  SMA20: N/A")
            print(f"  ATR: {atr.value if atr else 'N/A'}")
            if regime:
                print(f"  Regime Score: {regime.value:.1f}%")
            print(f"  Signal: {'BUY' if condition_met else 'NO BUY'}")
            return {
                'symbol': symbol,
                'price': price,
                'sma20': sma20_val,
                'atr': atr.value if atr else None,
                'regime': regime.value if regime else None,
                'condition_met': condition_met
            }
        except Exception as e:
            print(f"  ERROR analyzing: {e}")
            return None
    result = asyncio.run(fetch_and_analyze())
    if result:
        print()  # blank line
    else:
        print()

print("\n=== Summary ===")
print("If conditions were met, a buy signal would have been generated.")
print("Due to yesterday's bug, these trades may not have executed even if signaled.")
print("Now that the bug is fixed, the system would trade automatically if running.")
