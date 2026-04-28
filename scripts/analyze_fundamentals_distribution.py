#!/usr/bin/env python3
"""
Analyze fundamental data distribution across the stock universe to optimize
PE ratio and revenue growth thresholds for the value_quality_news strategy.
"""

import asyncio
import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from finance_service.core.yaml_config import YAMLConfigEngine
from finance_service.agents.data_agent import DataAgent
from finance_service.agents.analysis_agent import AnalysisAgent

async def fetch_fundamentals_for_symbols(symbols, start_date, end_date):
    """Fetch latest fundamentals for each symbol (uses most recent quarter)"""
    config = YAMLConfigEngine("config")
    data_agent = DataAgent(config)
    
    fundamentals_store = {}
    for i, sym in enumerate(symbols):
        print(f"Fetching fundamentals for {sym} ({i+1}/{len(symbols)})")
        try:
            report = await data_agent.run(
                symbol=sym,
                start_date=start_date,
                end_date=end_date,
                interval="1day",
                use_cache=False
            )
            if report.status == "success" and "fundamentals" in report.payload:
                fundamentals_store[sym] = report.payload["fundamentals"]
            else:
                print(f"  No fundamentals for {sym}")
        except Exception as e:
            print(f"  Error: {e}")
    
    return fundamentals_store

def analyze_distributions(fundamentals_store):
    """Analyze PE ratio and revenue growth distributions"""
    data = []
    for sym, funds in fundamentals_store.items():
        pe = funds.get('pe_ratio')
        rg = funds.get('revenue_growth_yoy')
        if pe is not None and rg is not None:
            data.append({
                'symbol': sym,
                'pe_ratio': pe,
                'revenue_growth_yoy': rg * 100  # Convert to percent
            })
    
    df = pd.DataFrame(data)
    if df.empty:
        print("No fundamental data available!")
        return None
    
    print("\n" + "="*60)
    print("FUNDAMENTAL DATA DISTRIBUTION (Latest)")
    print("="*60)
    print(f"\nSymbols with data: {len(df)}")
    
    print("\n--- P/E Ratio ---")
    print(df['pe_ratio'].describe())
    
    print("\n--- Revenue Growth YoY (%) ---")
    print(df['revenue_growth_yoy'].describe())
    
    # Suggest thresholds based on distribution
    print("\n" + "="*60)
    print("THRESHOLD RECOMMENDATIONS")
    print("="*60)
    
    pe_median = df['pe_ratio'].median()
    pe_q25 = df['pe_ratio'].quantile(0.25)
    pe_q75 = df['pe_ratio'].quantile(0.75)
    
    rg_median = df['revenue_growth_yoy'].median()
    rg_q25 = df['revenue_growth_yoy'].quantile(0.25)
    rg_q75 = df['revenue_growth_yoy'].quantile(75)
    
    print(f"\nP/E Ratio:")
    print(f"  Median: {pe_median:.1f}")
    print(f"  25th pct: {pe_q25:.1f}")
    print(f"  75th pct: {pe_q75:.1f}")
    print(f"\n  Current entry threshold: <30")
    print(f"  Current exit threshold: >50")
    print(f"\n  Suggested entry: < {pe_median:.1f} (median) or < {pe_q25:.1f} (25th pct)")
    print(f"  Suggested exit: > {pe_q75:.1f} (75th pct)")
    
    print(f"\nRevenue Growth YoY (%):")
    print(f"  Median: {rg_median:.1f}%")
    print(f"  25th pct: {rg_q25:.1f}%")
    print(f"  75th pct: {rg_q75:.1f}%")
    print(f"\n  Current entry threshold: >10%")
    print(f"  Current exit threshold: <0%")
    print(f"\n  Suggested entry: > {max(10, rg_median):.1f}% (median or higher)")
    print(f"  Suggested exit: < {min(0, rg_q25):.1f}% (25th pct or lower)")
    
    return df

async def main():
    symbols = [
        "NVDA", "PLTR", "UPST", "AVGO", "MSTR",
        "TSM", "QCOM", "AMD", "ASR", "ASML",
        "CRWD", "DDOG", "NET", "MDB", "SNOW",
        "MSFT", "GOOGL", "AAPL", "AMZN", "META"
    ]
    
    # Fetch a recent date range (just to get latest fundamentals)
    start_date = "2024-01-01"
    end_date = "2024-12-31"
    
    print("Fetching fundamental data for analysis...")
    fundamentals_store = await fetch_fundamentals_for_symbols(symbols, start_date, end_date)
    
    df = analyze_distributions(fundamentals_store)
    
    if df is not None:
        # Save to CSV for reference
        output_file = Path("/tmp/fundamentals_distribution_2024.csv")
        df.to_csv(output_file, index=False)
        print(f"\nSaved detailed data to {output_file}")

if __name__ == "__main__":
    asyncio.run(main())
