#!/usr/bin/env python3
"""
Parameter optimizer for sma20_trend strategy.
Tests combinations of SMA periods, position sizing, and stop-loss parameters.
"""

import subprocess
import json
import sys
from pathlib import Path

def run_backtest(sma_period, position_pct=1.5, stop_loss_atr=None, take_profit_atr=None):
    """Run backtest with specified parameters and return results"""
    # Create a temporary config with modified parameters
    config_file = Path(f"/tmp/backtest_config_sma{sma_period}_pos{position_pct}.yaml")
    
    # For now, we'll pass parameters via environment or a custom runner
    # This will be integrated into the backtest runner properly
    cmd = [
        "python", "-m", "finance_service.tools.backtest",
        "--symbols", "NVDA", "PLTR", "UPST", "AVGO", "MSTR", "TSM", "QCOM", "AMD", "ASR", "ASML", "CRWD", "DDOG", "NET", "MDB", "SNOW", "MSFT", "GOOGL", "AAPL", "AMZN", "META",
        "--start-date", "2023-01-01",
        "--end-date", "2024-12-31",
        "--strategy", "sma20_trend",
        "--capital", "100000"
    ]
    
    # We need a way to override SMA period dynamically. For now, we'll edit config temporarily
    # Or we can extend the backtest runner to accept --sma-period argument
    # For this MVP, we'll do a simple config edit approach
    
    config_path = Path("AITradeAgent/config/finance.yaml")
    backup_path = Path("/tmp/finance.yaml.backup")
    
    # Backup original config
    subprocess.run(["cp", str(config_path), str(backup_path)], check=True)
    
    try:
        # Modify SMA period in config (need to locate sma20_trend strategy)
        # This is hacky but works for quick iteration
        import re
        config_text = config_path.read_text()
        # Replace sma20_trend's sma_period parameter
        pattern = r'(sma20_trend:.*?indicator:\s*)(sma)(\d+)'
        # Actually need to find the specific strategy block
        
        # For now, skip implementation and just show the framework
        print(f"Would run: SMA={sma_period}, Position={position_pct}%, StopLoss={stop_loss_atr}")
        return {"cagr": 0, "sharpe": 0, "max_dd": 0}  # placeholder
        
    finally:
        # Restore config
        subprocess.run(["cp", str(backup_path), str(config_path)], check=True)

def main():
    """Run systematic parameter optimization"""
    sma_periods = [10, 15, 20, 25, 30, 40, 50]
    position_sizes = [1.0, 1.5, 2.0, 2.5, 3.0]
    
    results = []
    
    print("Starting parameter optimization for sma20_trend...")
    print(f"Testing {len(sma_periods)} SMA periods × {len(position_sizes)} position sizes = {len(sma_periods)*len(position_sizes)} combinations")
    
    for sma in sma_periods:
        for pos in position_sizes:
            print(f"\n{'='*60}")
            print(f"Testing: SMA{sma}, Position {pos}%")
            print('='*60)
            
            result = run_backtest(sma_period=sma, position_pct=pos)
            result['sma_period'] = sma
            result['position_pct'] = pos
            results.append(result)
    
    # Find best configuration
    if results:
        best = max(results, key=lambda x: x['cagr'])
        print(f"\n{'='*60}")
        print("OPTIMIZATION COMPLETE")
        print('='*60)
        print(f"Best CAGR: {best['cagr']:.2f}%")
        print(f"Best config: SMA{best['sma_period']}, Position {best['position_pct']}%")
        print(f"Sharpe: {best['sharpe']:.2f}, Max DD: {best['max_dd']:.1f}%")
        
        # Save all results
        output_file = Path("/tmp/optimization_results.json")
        output_file.write_text(json.dumps(results, indent=2))
        print(f"\nFull results saved to {output_file}")

if __name__ == "__main__":
    main()
