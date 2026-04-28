#!/usr/bin/env python3
"""
Quick Regime Detection Analysis using existing backtest data (2020-2024).
We'll fetch a representative sample of symbols to compute regime indicators.
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

from finance_service.core.yaml_config import YAMLConfigEngine
from finance_service.agents.data_agent import DataAgent

# Smaller sample for speed: 5 major symbols
SYMBOLS = ["NVDA", "MSFT", "GOOGL", "AAPL", "AMZN"]
START_DATE = "2020-01-01"
END_DATE = "2024-12-31"

def compute_regime_indicators(df):
    """Compute regime indicators from OHLCV DataFrame"""
    close = df['close'].sort_index()
    
    # 1. SMA200
    sma200 = close.rolling(window=200).mean()
    regime_sma200 = (close > sma200).map(lambda x: 1 if x else -1)
    
    # 2. 52-week high/low
    high_52w = df['high'].rolling(window=252).max()
    low_52w = df['low'].rolling(window=252).min()
    pct_from_high = (close - high_52w) / high_52w
    regime_52w = pd.Series(0, index=close.index)
    regime_52w[pct_from_high >= -0.10] = 1
    regime_52w[pct_from_high <= -0.20] = -1
    
    # 3. ADX with +DI/-DI
    try:
        from ta.trend import ADXIndicator
        adx_ind = ADXIndicator(high=df['high'], low=df['low'], close=close, window=14)
        adx = adx_ind.adx()
        plus_di = adx_ind.adx_pos()
        minus_di = adx_ind.adx_neg()
        strong_trend = adx > 25
        bullish = plus_di > minus_di
        regime_adx = pd.Series(0, index=close.index)
        regime_adx[strong_trend & bullish] = 1
        regime_adx[strong_trend & (~bullish)] = -1
    except Exception as e:
        print(f"ADX error: {e}")
        regime_adx = pd.Series(0, index=close.index)
    
    # 4. MACD cross
    try:
        from ta.trend import MACD
        macd_ind = MACD(close=close, window_slow=26, window_fast=12, window_sign=9)
        macd_line = macd_ind.macd()
        signal_line = macd_ind.macd_signal()
        regime_macd = (macd_line > signal_line).map(lambda x: 1 if x else -1)
    except Exception as e:
        print(f"MACD error: {e}")
        regime_macd = pd.Series(0, index=close.index)
    
    # 5. RSI midpoint
    try:
        from ta.momentum import RSIIndicator
        rsi_ind = RSIIndicator(close=close, window=14)
        rsi = rsi_ind.rsi()
        regime_rsi = pd.Series(0, index=close.index)
        regime_rsi[rsi > 50] = 1
        regime_rsi[rsi < 50] = -1
    except Exception as e:
        print(f"RSI error: {e}")
        regime_rsi = pd.Series(0, index=close.index)
    
    return {
        'close': close,
        'sma200': sma200,
        'regime_sma200': regime_sma200,
        'regime_52w': regime_52w,
        'regime_adx': regime_adx,
        'regime_macd': regime_macd,
        'regime_rsi': regime_rsi
    }

async def main():
    print("="*80)
    print("REGIME DETECTION ANALYSIS (Sample from 5 large caps)")
    print("="*80)
    
    config = YAMLConfigEngine("config")
    data_agent = DataAgent(config)
    
    all_data = {}
    
    for i, sym in enumerate(SYMBOLS, 1):
        print(f"[{i}/{len(SYMBOLS)}] Fetching {sym}...")
        try:
            # Note: Use correct interval "1d"
            report = await data_agent.run(
                symbol=sym,
                start_date=START_DATE,
                end_date=END_DATE,
                interval="1d",
                use_cache=False
            )
            if report.status == "success" and "dataframe" in report.payload:
                df_dict = report.payload["dataframe"]
                df = pd.DataFrame.from_dict(df_dict)
                df.index = pd.to_datetime(df.index)
                df = df.sort_index()
                if len(df) > 200:
                    all_data[sym] = df
                    print(f"  ✓ Got {len(df)} bars")
                else:
                    print(f"  ✗ Insufficient data ({len(df)} bars)")
        except Exception as e:
            print(f"  ✗ Error: {e}")
    
    if not all_data:
        print("No data fetched. Exiting.")
        return
    
    print(f"\nFetched data for {len(all_data)} symbols")
    
    # Compute indicators for each symbol
    indicators_dict = {}
    for sym, df in all_data.items():
        indicators = compute_regime_indicators(df)
        indicators_dict[sym] = indicators
    
    # Create combined benchmark (equal-weight portfolio)
    print("\nCreating benchmark portfolio...")
    first_sym = list(indicators_dict.keys())[0]
    dates = indicators_dict[first_sym]['close'].index
    
    combined_prices = pd.DataFrame(index=dates)
    for sym, ind in indicators_dict.items():
        combined_prices[sym] = ind['close']
    
    normalized = combined_prices / combined_prices.iloc[0]
    combined_equity = normalized.mean(axis=1)
    
    # Determine bull/bear periods based on 20% drawdown rule
    rolling_max = combined_equity.expanding().max()
    drawdown = (combined_equity - rolling_max) / rolling_max
    is_bear = drawdown < -0.20
    regime_benchmark = is_bear.map(lambda x: -1 if x else 1)
    
    # Aggregate regime signals across symbols
    print("Aggregating regime signals...")
    combined_sma200 = pd.Series(0, index=dates)
    combined_52w = pd.Series(0, index=dates)
    combined_adx = pd.Series(0, index=dates)
    combined_macd = pd.Series(0, index=dates)
    combined_rsi = pd.Series(0, index=dates)
    
    for sym, ind in indicators_dict.items():
        combined_sma200 += ind['regime_sma200']
        combined_52w += ind['regime_52w']
        combined_adx += ind['regime_adx']
        combined_macd += ind['regime_macd']
        combined_rsi += ind['regime_rsi']
    
    n = len(indicators_dict)
    combined_sma200 /= n
    combined_52w /= n
    combined_adx /= n
    combined_macd /= n
    combined_rsi /= n
    
    # Evaluate correlation of each indicator with benchmark
    print("\n" + "="*80)
    print("INDICATOR EVALUATION (Correlation with 20% drawdown bear/bear)")
    print("="*80)
    
    results = []
    for name, series in [
        ('SMA200', combined_sma200),
        ('52-week H/L', combined_52w),
        ('ADX+DI', combined_adx),
        ('MACD cross', combined_macd),
        ('RSI 50', combined_rsi)
    ]:
        # Align and drop NaNs
        aligned = pd.concat([series, regime_benchmark], axis=1).dropna()
        aligned.columns = ['indicator', 'benchmark']
        
        if len(aligned) > 0:
            corr = aligned['indicator'].corr(aligned['benchmark'])
            accuracy = (aligned['indicator'] == aligned['benchmark']).mean()
            results.append((name, corr, accuracy))
            print(f"{name:20s}: Corr={corr:+.3f}, Accuracy={accuracy:.2%}")
        else:
            print(f"{name:20s}: No data")
    
    # Find best
    if results:
        best = max(results, key=lambda x: x[1])  # Highest correlation
        print(f"\n🏆 Best indicator: {best[0]} (correlation={best[1]:+.3f})")
    
    # Create composite score (weighted average of top 3)
    print("\n" + "="*80)
    print("COMPOSITE REGIME SCORE")
    print("="*80)
    
    # Use weights based on correlation (normalized)
    weights = {}
    total_weight = 0
    for name, corr, acc in results:
        w = max(0, corr)  # Only positive correlation
        weights[name] = w
        total_weight += w
    
    if total_weight > 0:
        for name in weights:
            weights[name] /= total_weight
        print(f"Weights: {weights}")
        
        # Compute composite score
        composite = pd.Series(0.0, index=dates)
        composites = {
            'SMA200': combined_sma200,
            '52-week H/L': combined_52w,
            'ADX+DI': combined_adx,
            'MACD cross': combined_macd,
            'RSI 50': combined_rsi
        }
        for name, weight in weights.items():
            composite += composites[name] * weight
        
        # Convert to 0-100% scale
        composite_pct = ((composite + 1) / 2 * 100).clip(0, 100)
        
        print(f"\nComposite score range: {composite.min():.2f} to {composite.max():.2f}")
        print(f"As percentage (0-100%): {composite_pct.min():.1f}% to {composite_pct.max():.1f}%")
        
        # Sample output
        print("\nSample (first 5 days of 2020):")
        sample = composite_pct.head()
        for date, val in sample.items():
            print(f"  {date.date()}: {val:.1f}%")
        
        # Threshold analysis
        print("\n" + "="*80)
        print("THRESHOLD ANALYSIS")
        print("="*80)
        
        for bull_thresh in [60, 70, 80]:
            bear_thresh = 100 - bull_thresh
            signal = pd.Series(0, index=composite_pct.index)
            signal[composite_pct > bull_thresh] = 1
            signal[composite_pct < bear_thresh] = -1
            
            # Accuracy
            aligned_sig = pd.concat([signal, regime_benchmark], axis=1).dropna()
            aligned_sig.columns = ['signal', 'benchmark']
            non_neutral = aligned_sig['signal'] != 0
            if non_neutral.sum() > 0:
                acc = (aligned_sig.loc[non_neutral, 'signal'] == aligned_sig.loc[non_neutral, 'benchmark']).mean()
                bull_pct = (signal == 1).mean() * 100
                neutral_pct = (signal == 0).mean() * 100
                print(f"Bull>{bull_thresh}%, Bear<{bear_thresh}%: Acc={acc:.2%}, Bull signal={bull_pct:.1f}%, Neutral={neutral_pct:.1f}%")
        
        # Save composite to CSV
        output = pd.DataFrame({
            'date': composite_pct.index,
            'regime_pct': composite_pct.values,
            'raw_score': composite.values,
            'benchmark': regime_benchmark.values,
            'portfolio_eq': combined_equity.values
        })
        output_file = Path("/tmp/composite_regime_score.csv")
        output.to_csv(output_file, index=False)
        print(f"\nComposite regime scores saved to {output_file}")
        
        print("\n" + "="*80)
        print("CONCLUSIONS FOR IMPLEMENTATION")
        print("="*80)
        print("1. Use composite score from multiple indicators for robustness")
        print("2. Recommended threshold: Bull >70%, Bear <30% (adjust based on accuracy)")
        print("3. Output: 0-100% probability, convertible to binary or ternary signals")
        print("4. Quickest detection: SMA200 alone (least lag) but composite is more reliable")
        print("\nImplementation plan:")
        print("  - Compute regime score daily using SMA200, ADX+DI, and 52-wk H/L (top performers)")
        print("  - Output: score between 0-100%")
        print("  - Meta-strategy: only enable sma50_trend when score > 70%")
        print("  - When score < 30%, go to cash (avoid bear markets)")
        
    else:
        print("No valid results to compute composite.")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
