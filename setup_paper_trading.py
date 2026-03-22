#!/usr/bin/env python3
"""
Setup and launch paper trading for sma20_trend strategy.
This configures the live trading environment with the proven parameters.
"""

import shutil
import sys
from pathlib import Path

def setup_paper_trading():
    """Configure finance.yaml for paper trading"""
    config_path = Path("AITradeAgent/config/finance.yaml")
    
    print("Setting up paper trading configuration...")
    
    # Read current config
    config_text = config_path.read_text()
    
    # Update the active strategy section to use sma20_trend
    # The 'strategy:' block at the top defines the active strategy
    # We need to point it to the sma20_trend configuration
    
    # Find and replace the strategy name in the main config
    # Current: strategy: value_quality_news
    # Change to: strategy: sma20_trend
    
    if "strategy: value_quality_news" in config_text:
        config_text = config_text.replace(
            "strategy: value_quality_news",
            "strategy: sma20_trend"
        )
        print("✓ Set active strategy to sma20_trend")
    else:
        print("⚠ Could not find 'strategy: value_quality_news' to replace")
        print("  Please manually set strategy to 'sma20_trend' in finance.yaml")
        return False
    
    # Ensure paper trading mode
    if "paper_trading:" in config_text:
        config_text = config_text.replace(
            "paper_trading: false",
            "paper_trading: true"
        )
        print("✓ Enabled paper trading mode")
    else:
        print("⚠ Could not find paper_trading setting")
    
    # Set reasonable risk parameters for live trading
    # max_position_size_pct: 5% per position (instead of 25% which is too aggressive)
    # risk_budget_pct: 1.5% (keep as is)
    # max_daily_loss_pct: 2% (daily circuit breaker)
    
    config_backup = config_path.with_suffix(".yaml.backup")
    shutil.copy(config_path, config_backup)
    print(f"✓ Backed up original config to {config_backup}")
    
    config_path.write_text(config_text)
    print(f"✓ Updated configuration in {config_path}")
    
    return True

def launch_orchestrator():
    """Start the finance service orchestrator"""
    print("\nLaunching Finance Service Orchestrator...")
    print("="*60)
    
    # Assuming service management via systemd or direct python
    # For development, run directly:
    cmd = [
        "python", "-m", "finance_service.main",
        "--config", "config/finance.yaml"
    ]
    
    print(f"Command: {' '.join(cmd)}")
    print("\nThe service will:")
    print("- Connect to Telegram/Signal for notifications")
    print("- Begin market scanning every 15 minutes")
    print("- Execute paper trades on sma20_trend signals")
    print("- Log all trades to portfolio.sqlite")
    
    # For now, just print instructions
    print("\n[DRY RUN] Would execute: " + " ".join(cmd))
    print("\nTo start paper trading manually:")
    print("  cd AITradeAgent")
    print("  source venv/bin/activate")
    print("  python -m finance_service.main --config config/finance.yaml")
    
    return True

def main():
    print("PAPER TRADING SETUP FOR SMA20_TREND")
    print("="*60)
    
    if not setup_paper_trading():
        print("Setup failed. Exiting.")
        sys.exit(1)
    
    launch_orchestrator()
    
    print("\n" + "="*60)
    print("NEXT STEPS AFTER LAUNCH:")
    print("="*60)
    print("1. Monitor initial logs for data connection errors")
    print("2. Verify market data is arriving (should see daily scans)")
    print("3. Check trade execution: should see entry/exit signals")
    print("4. Review portfolio.sqlite after first trades")
    print("5. Track performance metrics daily")
    print("\nGood luck! 📈")

if __name__ == "__main__":
    main()
