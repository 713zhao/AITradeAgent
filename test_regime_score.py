#!/usr/bin/env python3
"""Quick test: compute regime_score for NVDA on first few days of 2020"""
import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from finance_service.core.yaml_config import YAMLConfigEngine
from finance_service.agents.data_agent import DataAgent
from finance_service.agents.analysis_agent import AnalysisAgent

async def test():
    config = YAMLConfigEngine("config")
    data_agent = DataAgent(config)
    
    print("Fetching NVDA data (full period)...")
    report = await data_agent.run(
        symbol="NVDA",
        start_date="2020-01-01",
        end_date="2024-12-31",
        interval="1d",
        use_cache=False
    )
    
    if report.status == "success" and "dataframe" in report.payload:
        df_dict = report.payload["dataframe"]
        df = pd.DataFrame.from_dict(df_dict)
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        
        print(f"Data shape: {df.shape}")
        print(f"Date range: {df.index[0]} to {df.index[-1]}")
        
        analysis_agent = AnalysisAgent()
        
        # Compute indicators for each day
        for i in range(200, len(df)+1):
            df_sub = df.iloc[:i]
            try:
                snapshot = analysis_agent._calculate_all(df_sub, "NVDA")
                regime_val = snapshot.indicators.get('regime_score')
                if regime_val:
                    print(f"{df.index[i-1].date()}: regime_score={regime_val.value:.1f}, signal={regime_val.signal}")
                else:
                    print(f"{df.index[i-1].date()}: No regime_score computed")
            except Exception as e:
                print(f"{df.index[i-1].date()}: Error - {e}")
                break

if __name__ == "__main__":
    import asyncio
    asyncio.run(test())
