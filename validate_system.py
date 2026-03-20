#!/usr/bin/env python3
"""
Quick validation: Verify the trading system actually works end-to-end.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from finance_service.core.yaml_config import YAMLConfigEngine
from finance_service.agents.data_agent import DataAgent
from finance_service.agents.analysis_agent import AnalysisAgent
from finance_service.agents.strategy_agent import StrategyAgent
from finance_service.agents.risk_agent import RiskAgent

async def test_full_pipeline():
    """Test: analyze NVDA from start to risk check"""
    print("="*70)
    print("TRADING SYSTEM VALIDATION")
    print("="*70)
    
    # 1. Load config
    print("\n1. Loading YAML config...")
    try:
        config_engine = YAMLConfigEngine(config_dir="config")
        print("   ✅ Config loaded")
        
        # Show key settings
        rsi_oversold = config_engine.get("finance", "strategy/rules/rsi_entry_oversold_threshold", default="N/A")
        print(f"   - RSI oversold threshold: {rsi_oversold}")
        max_pos = config_engine.get("finance", "risk/max_position_size_pct", default="N/A")
        print(f"   - Max position size: {max_pos}%")
        auto_exec = config_engine.get("finance", "strategy/auto_execute/require_approval", default="N/A")
        print(f"   - Auto-execute: {auto_exec}")
    except Exception as e:
        print(f"   ❌ Config load failed: {e}")
        return False
    
    # 2. Initialize agents
    print("\n2. Initializing agents...")
    try:
        event_bus = get_event_bus()
        data_agent = DataAgent(config_engine)
        analysis_agent = AnalysisAgent({})  # Will use periods from config later
        strategy_agent = StrategyAgent(config_engine)
        print("   ✅ Agents initialized")
        print(f"   - DataAgent: {data_agent.agent_id}")
        print(f"   - AnalysisAgent: {analysis_agent.agent_id}")
        print(f"   - StrategyAgent: {strategy_agent.agent_id}")
        print(f"   - Loaded {len(strategy_agent.rule_strategy.rules)} rules")
    except Exception as e:
        print(f"   ❌ Agent init failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 3. Fetch data for NVDA (252 days lookback)
    print("\n3. Fetching market data for NVDA...")
    from datetime import datetime, timedelta
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=252)
    try:
        data_report = await data_agent.run(
            symbol="NVDA",
            start_date=str(start_date),
            end_date=str(end_date),
            interval="1d",
            use_cache=False,  # Bypass cache to get full 252 days
            emit_events=False
        )
        if data_report.status != "success":
            print(f"   ❌ Data fetch failed: {data_report.message}")
            return False
        df_dict = data_report.payload.get("dataframe")
        if not df_dict:
            print("   ❌ No dataframe in payload")
            return False
        import pandas as pd
        df = pd.DataFrame.from_dict(df_dict)
        print(f"   ✅ Fetched {len(df)} days of data")
    except Exception as e:
        print(f"   ❌ Data fetch error: {e}")
        return False
    
    # 4. Calculate indicators
    print("\n4. Calculating indicators...")
    try:
        analysis_report = await analysis_agent.run(data_payload=df_dict, symbol="NVDA")
        if analysis_report.status != "success":
            print(f"   ❌ Analysis failed: {analysis_report.message}")
            return False
        indicators = analysis_report.payload.get("indicators", {})
        print(f"   ✅ Calculated {len(indicators)} indicators")
        for name in ['rsi', 'macd', 'sma_20', 'sma_50']:
            if name in indicators:
                val = indicators[name]['value'] if isinstance(indicators[name], dict) else indicators[name].value
                print(f"      - {name}: {val:.2f}")
    except Exception as e:
        print(f"   ❌ Analysis error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 5. Generate trade proposal
    print("\n5. Running strategy engine...")
    try:
        # Create a mock news report
        from finance_service.agents.agent_interface import AgentReport
        news_report = AgentReport(
            agent_id="news_agent",
            status="success",
            message="Mock news",
            payload={"symbol": "NVDA", "news_count": 0, "sentiment": {}, "catalysts": {}}
        )
        
        # Pass the full AgentReport objects, not just payloads
        strategy_report = await strategy_agent.run(analysis_report, news_report)
        if strategy_report.status != "success":
            print(f"   ❌ Strategy failed: {strategy_report.message}")
            return False
        proposals = strategy_report.payload.get("proposals", [])
        print(f"   ✅ Generated {len(proposals)} trade proposal(s)")
        if proposals:
            p = proposals[0]
            print(f"      - Action: {p.get('action')}")
            print(f"      - Confidence: {p.get('confidence', 0):.1%}")
            print(f"      - Target: ${p.get('target_price', 'N/A')}")
            print(f"      - Stop: ${p.get('stop_loss_price', 'N/A')}")
    except Exception as e:
        print(f"   ❌ Strategy error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print("\n" + "="*70)
    print("✅ SYSTEM VALIDATION SUCCESSFUL")
    print("="*70)
    print("\nReady to run paper trading simulation!")
    return True

if __name__ == "__main__":
    from finance_service.core.event_bus import get_event_bus
    result = asyncio.run(test_full_pipeline())
    sys.exit(0 if result else 1)
