#!/usr/bin/env python3
"""
Regime Detection Analysis: Evaluate different methods for bull/bear market identification
using historical data from our 20-symbol universe (2020-2024).

Goal: Find the fastest (least lag) and most accurate regime detection method.
Also evaluate if we can output a 0-100% probability score instead of binary.
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Optional matplotlib
try:
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

sys.path.insert(0, str(Path(__file__).parent))

from finance_service.core.yaml_config import YAMLConfigEngine
from finance_service.agents.data_agent import DataAgent

# Universe
SYMBOLS = [
    "NVDA", "PLTR", "UPST", "AVGO", "MSTR", "TSM", "QCOM", "AMD", "ASR", "ASML",
    "CRWD", "DDOG", "NET", "MDB", "SNOW", "MSFT", "GOOGL", "AAPL", "AMZN", "META"
]

# Date range covering bull/bear cycles
START_DATE = "2020-01-01"
END_DATE = "2024-12-31"

# Define bull/bear periods based on SPY or NASDAQ composite for ground truth
# For simplicity, we'll use a simple definition: Bear = >20% drawdown from peak
# This is a common definition used by institutions

def compute_regime_indicators(df, symbol):
    """Compute various regime detection indicators"""
    # Ensure sorted by date
    df = df.sort_index()
    close = df['close']
    
    # 1. SMA200 filter
    sma200 = close.rolling(window=200).mean()
    above_sma200 = close > sma200
    regime_sma200 = above_sma200.map(lambda x: 1 if x else -1)
    
    # 2. 52-week high/low (252 trading days)
    high_52w = close.rolling(window=252).max()
    low_52w = close.rolling(window=252).min()
    # Within 10% of 52w high = bull, >20% below = bear
    pct_from_high = (close - high_52w) / high_52w
    regime_52w = pd.Series(0, index=close.index)
    regime_52w[pct_from_high >= -0.10] = 1  # Within 10% of high = bull
    regime_52w[pct_from_high <= -0.20] = -1  # >20% below = bear
    
    # 3. ADX (Average Directional Index) - trend strength
    # Need to compute from High/Low/Close
    if 'high' in df.columns and 'low' in df.columns:
        high = df['high']
        low = df['low']
        # ADX calculation (14-period)
        from ta.trend import ADXIndicator
        adx_ind = ADXIndicator(high=high, low=low, close=close, window=14)
        adx = adx_ind.adx()
        # +DI and -DI
        plus_di = adx_ind.adx_pos()
        minus_di = adx_ind.adx_neg()
        
        # Regime: ADX > 25 means strong trend
        strong_trend = adx > 25
        # Direction: +DI > -DI = bullish, else bearish
        bullish = plus_di > minus_di
        regime_adx = pd.Series(0, index=close.index)
        regime_adx[strong_trend & bullish] = 1
        regime_adx[strong_trend & (~bullish)] = -1
    else:
        regime_adx = pd.Series(0, index=close.index)
    
    # 4. Volatility Regime using ATR/Price ratio
    atr_period = 14
    from ta.volatility import AverageTrueRange
    atr_ind = AverageTrueRange(high=df['high'] if 'high' in df.columns else close,
                               low=df['low'] if 'low' in df.columns else close,
                               close=close,
                               window=atr_period)
    atr = atr_ind.average_true_range()
    atr_ratio = atr / close
    # High volatility (>5%) = stress regime, Low (<2%) = calm
    # We'll create a continuous score from this
    
    # 5. MACD cross (trend following)
    from ta.trend import MACD
    macd_ind = MACD(close=close, window_slow=26, window_fast=12, window_sign=9)
    macd_line = macd_ind.macd()
    signal_line = macd_ind.macd_signal()
    macd_bullish = macd_line > signal_line
    regime_macd = macd_bullish.map(lambda x: 1 if x else -1)
    
    # 6. RSI (overbought/oversold)
    from ta.momentum import RSIIndicator
    rsi_ind = RSIIndicator(close=close, window=14)
    rsi = rsi_ind.rsi()
    regime_rsi = pd.Series(0, index=close.index)
    regime_rsi[rsi > 50] = 1
    regime_rsi[rsi < 50] = -1
    
    # Composite score (weighted average)
    # We'll give SMA200 the most weight, then ADX for trend strength confirmation
    weights = {
        'sma200': 0.40,
        'adx': 0.30,
        '52w': 0.20,
        'macd': 0.05,
        'rsi': 0.05
    }
    regime_score = (
        regime_sma200 * weights['sma200'] +
        regime_adx.clip(-1, 1) * weights['adx'] +
        regime_52w.clip(-1, 1) * weights['52w'] +
        regime_macd.clip(-1, 1) * weights['macd'] +
        regime_rsi.clip(-1, 1) * weights['rsi']
    )
    
    # Convert to percentage (0-100% bullish probability)
    regime_pct = (regime_score + 1) / 2 * 100
    
    return {
        'close': close,
        'sma200': sma200,
        'regime_sma200': regime_sma200,
        'regime_52w': regime_52w,
        'regime_adx': regime_adx,
        'regime_macd': regime_macd,
        'regime_rsi': regime_rsi,
        'regime_score': regime_score,
        'regime_pct': regime_pct,
        'atr_ratio': atr_ratio
    }

def compute_ground_truth_benchmark(combined_returns):
    """
    Create a benchmark bull/bear classification based on major index cycles.
    Using a simple peak-to-trough >20% drawdown as bear definition.
    """
    # Compute rolling max and drawdown
    rolling_max = combined_returns.expanding().max()
    drawdown = (combined_returns - rolling_max) / rolling_max
    
    # Bear regime when drawdown > -20%
    is_bear = drawdown < -0.20
    regime_benchmark = is_bear.map(lambda x: -1 if x else 1)
    
    return regime_benchmark, drawdown

def evaluate_regime_indicator(indicator_series, benchmark_series, name):
    """Evaluate accuracy, lag, and correlation of a regime indicator"""
    # Align to same dates
    aligned = pd.concat([indicator_series, benchmark_series], axis=1).dropna()
    aligned.columns = ['indicator', 'benchmark']
    
    if aligned.empty:
        return None
    
    # Accuracy (on days where both agree/disagree)
    accuracy = (aligned['indicator'] == aligned['benchmark']).mean()
    
    # Correlation
    correlation = aligned['indicator'].corr(aligned['benchmark'])
    
    # Lag analysis: How many days does indicator change after benchmark?
    # We'll compute the average delay of correct signals
    indicator_changes = aligned['indicator'].diff() != 0
    benchmark_changes = aligned['benchmark'].diff() != 0
    
    # Simple lag estimate: look at leading indicator
    # We'll compute cross-correlation
    cross_corr = pd.concat([
        aligned['indicator'].shift(i) for i in range(-10, 11)
    ], axis=1).corrwith(aligned['benchmark']).abs()
    
    best_lag = cross_corr.idxmax() if not cross_corr.empty else 0
    
    return {
        'name': name,
        'accuracy': accuracy,
        'correlation': correlation,
        'best_lag': best_lag,  # negative means indicator leads
        'total_days': len(aligned),
        'bull_pct': (aligned['indicator'] == 1).mean() * 100,
        'benchmark_bull_pct': (aligned['benchmark'] == 1).mean() * 100
    }

async def main():
    print("="*80)
    print("REGIME DETECTION ANALYSIS")
    print("="*80)
    print(f"Universe: {len(SYMBOLS)} symbols")
    print(f"Period: {START_DATE} to {END_DATE}")
    print()
    
    # Fetch data for all symbols
    config = YAMLConfigEngine("config")
    data_agent = DataAgent(config)
    
    all_indicators = {}
    
    print("Fetching historical data and computing regime indicators...")
    for i, sym in enumerate(SYMBOLS, 1):
        print(f"[{i}/{len(SYMBOLS)}] {sym}...")
        try:
            report = await data_agent.run(
                symbol=sym,
                start_date=START_DATE,
                end_date=END_DATE,
                interval="1day",
                use_cache=False
            )
            if report.status == "success" and "dataframe" in report.payload:
                df_dict = report.payload["dataframe"]
                df = pd.DataFrame.from_dict(df_dict)
                df.index = pd.to_datetime(df.index)
                df = df.sort_index()
                
                if len(df) > 200:
                    indicators = compute_regime_indicators(df, sym)
                    all_indicators[sym] = indicators
        except Exception as e:
            print(f"  Error: {e}")
    
    if not all_indicators:
        print("No data fetched. Exiting.")
        return
    
    # Combine regime scores across symbols (simple average)
    print("\nCombining regime scores across universe...")
    first_key = list(all_indicators.keys())[0]
    dates = all_indicators[first_key]['close'].index
    
    # Create combined equity curve for ground truth benchmark
    combined_prices = pd.DataFrame(index=dates)
    for sym, ind in all_indicators.items():
        combined_prices[sym] = ind['close']
    
    # Normalize to start at 1.0
    normalized = combined_prices / combined_prices.iloc[0]
    combined_equity = normalized.mean(axis=1)  # Equal-weight portfolio
    
    # Compute benchmark regime
    regime_benchmark, drawdown = compute_ground_truth_benchmark(combined_equity)
    
    # Aggregate indicators across symbols
    combined_regime_sma200 = pd.Series(0, index=dates)
    combined_regime_52w = pd.Series(0, index=dates)
    combined_regime_adx = pd.Series(0, index=dates)
    combined_regime_macd = pd.Series(0, index=dates)
    combined_regime_rsi = pd.Series(0, index=dates)
    combined_regime_score = pd.Series(0.0, index=dates)
    combined_regime_pct = pd.Series(0.0, index=dates)
    
    for sym, ind in all_indicators.items():
        combined_regime_sma200 += ind['regime_sma200']
        combined_regime_52w += ind['regime_52w']
        combined_regime_adx += ind['regime_adx']
        combined_regime_macd += ind['regime_macd']
        combined_regime_rsi += ind['regime_rsi']
        combined_regime_score += ind['regime_score']
        combined_regime_pct += ind['regime_pct']
    
    n = len(all_indicators)
    combined_regime_sma200 /= n
    combined_regime_52w /= n
    combined_regime_adx /= n
    combined_regime_macd /= n
    combined_regime_rsi /= n
    combined_regime_score /= n
    combined_regime_pct /= n
    
    # Evaluate each indicator against benchmark
    print("\n" + "="*80)
    print("REGIME INDICATOR EVALUATION")
    print("="*80)
    
    evaluations = []
    for name, series in [
        ('SMA200', combined_regime_sma200),
        ('52-week High/Low', combined_regime_52w),
        ('ADX+DI', combined_regime_adx),
        ('MACD cross', combined_regime_macd),
        ('RSI 50', combined_regime_rsi),
        ('Composite score', combined_regime_score)
    ]:
        eval_result = evaluate_regime_indicator(series, regime_benchmark, name)
        if eval_result:
            evaluations.append(eval_result)
            print(f"\n{name}:")
            print(f"  Accuracy: {eval_result['accuracy']:.2%}")
            print(f"  Correlation: {eval_result['correlation']:.3f}")
            print(f"  Best lag: {eval_result['best_lag']} days (negative = leads)")
            print(f"  Bullish %: {eval_result['bull_pct']:.1f}% (benchmark: {eval_result['benchmark_bull_pct']:.1f}%)")
    
    # Find best indicator (highest correlation, lowest lag)
    if evaluations:
        best = max(evaluations, key=lambda x: (x['correlation'], -abs(x['best_lag'])))
        print("\n" + "="*80)
        print("🏆 BEST REGIME INDICATOR")
        print("="*80)
        print(f"{best['name']} (Corr: {best['correlation']:.3f}, Lag: {best['best_lag']} days)")
    
    # Create regime probability series (0-100%)
    print("\n" + "="*80)
    print("REGIME PROBABILITY OUTPUT")
    print("="*80)
    print(f"Composite score range: {combined_regime_score.min():.2f} to {combined_regime_score.max():.2f}")
    print(f"Converted to 0-100%: {combined_regime_pct.min():.1f}% to {combined_regime_pct.max():.1f}%")
    
    # Show sample dates
    print("\nSample output (first 10 trading days of 2020):")
    sample = combined_regime_pct.head(10)
    for date, score in sample.items():
        print(f"  {date.date()}: {score:.1f}% bullish")
    
    # Calculate threshold optimizations
    print("\n" + "="*80)
    print("THRESHOLD OPTIMIZATION FOR BULL/BEAR CLASSIFICATION")
    print("="*80)
    
    thresholds = [30, 40, 50, 60, 70]
    best_threshold = 50
    best_accuracy = 0
    
    for thresh in thresholds:
        # Classify as bull if > thresh%, bear if < (100-thresh)%, neutral in between
        signal = pd.Series(0, index=combined_regime_pct.index)
        signal[combined_regime_pct > thresh] = 1
        signal[combined_regime_pct < (100 - thresh)] = -1
        # Neutral between thresholds
        
        # Evaluate accuracy only on non-neutral days
        non_neutral = signal != 0
        if non_neutral.sum() > 0:
            aligned_signal = signal[non_neutral]
            aligned_benchmark = regime_benchmark[non_neutral]
            accuracy = (aligned_signal == aligned_benchmark).mean()
            bull_pct = (signal == 1).mean() * 100
            print(f"Threshold {thresh}%: Accuracy {accuracy:.2%}, Bull signal {bull_pct:.1f}%")
            
            if accuracy > best_accuracy:
                best_accuracy = accuracy
                best_threshold = thresh
    
    print(f"\nRecommended threshold: {best_threshold}% (Accuracy: {best_accuracy:.2%})")
    
    # Save results to CSV for review
    output_df = pd.DataFrame({
        'date': combined_regime_pct.index,
        'regime_pct': combined_regime_pct.values,
        'regime_score': combined_regime_score.values,
        'sma200_regime': combined_regime_sma200.values,
        'adx_regime': combined_regime_adx.values,
        'regime_benchmark': regime_benchmark.values,
        'combined_equity': combined_equity.values,
        'drawdown': drawdown.values
    })
    output_file = Path("/tmp/regime_analysis_2020_2024.csv")
    output_df.to_csv(output_file, index=False)
    print(f"\n Detailed analysis saved to {output_file}")
    
    # Create plot (optional)
    if HAS_MATPLOTLIB:
        try:
            fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True)
            
            # Plot 1: Combined equity with regime highlighting
            ax1 = axes[0]
            ax1.plot(combined_equity.index, combined_equity.values, 'k-', label='Portfolio (20-symbol avg)')
            ax1.set_ylabel('Equity (normalized)')
            ax1.set_title('Portfolio Performance and Regime Detection')
            # Highlight bull/bear periods
            bull_periods = combined_regime_pct > 70
            bear_periods = combined_regime_pct < 30
            for idx in combined_equity.index[bull_periods]:
                ax1.axvspan(idx, idx, color='green', alpha=0.1)
            for idx in combined_equity.index[bear_periods]:
                ax1.axvspan(idx, idx, color='red', alpha=0.1)
            ax1.legend()
            
            # Plot 2: Regime probability score
            ax2 = axes[1]
            ax2.plot(combined_regime_pct.index, combined_regime_pct.values, 'b-', label='Bullish Probability')
            ax2.axhline(y=70, color='g', linestyle='--', alpha=0.5, label='Bull threshold (70%)')
            ax2.axhline(y=30, color='r', linestyle='--', alpha=0.5, label='Bear threshold (30%)')
            ax2.set_ylabel('Probability %')
            ax2.set_title('Regime Detection Score (0-100%)')
            ax2.legend()
            
            # Plot 3: Drawdown
            ax3 = axes[2]
            ax3.fill_between(drawdown.index, drawdown.values * 100, 0, color='red', alpha=0.3)
            ax3.set_ylabel('Drawdown %')
            ax3.set_xlabel('Date')
            ax3.set_title('Portfolio Drawdown')
            
            plt.tight_layout()
            plot_file = Path("/tmp/regime_analysis_plot.png")
            plt.savefig(plot_file, dpi=100)
            print(f"Plot saved to {plot_file}")
        except Exception as e:
            print(f"Plotting error: {e}")
    else:
        print("\n(Plotting skipped - matplotlib not available)")
    
    print("\n" + "="*80)
    print("RECOMMENDATIONS")
    print("="*80)
    print("Based on analysis:")
    print(f"1. Best regime indicator: {best['name']}")
    print(f"2. Use composite score with threshold: {best_threshold}% bull / {100-best_threshold}% bear")
    print(f"3. Expect ~{best_accuracy:.1%} accuracy on non-neutral days")
    print(f"4. Regime changes provide actionable signals for strategy switching")
    print("\nImplementation: Create a meta-strategy that reads regime_pct and enables:")
    print("  - Bull (>70%): sma50_trend")
    print("  - Bear (<30%): move to cash (no trades)")
    print("  - Neutral (30-70%): cautious small position or alternate strategy")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
