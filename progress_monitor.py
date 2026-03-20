#!/usr/bin/env python3
"""
Progress Monitor - Automated strategy performance check every 30 minutes.
Checks latest backtest results, compares to targets, and recommends adjustments.
"""

import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path

WORKSPACE = Path("/home/eric/.openclaw/workspace/AITradeAgent")
DB_PATH = WORKSPACE / "finance_service" / "storage" / "backtest.sqlite"
PROGRESS_LOG = WORKSPACE / "memory" / "progress_monitor.md"

TARGET_CAGR = 20.0  # %
TARGET_SHARPE = 1.0
TARGET_MAX_DD = 30.0

def get_latest_backtest():
    """Fetch most recent backtest run from database."""
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM backtest_runs 
        ORDER BY created_at DESC 
        LIMIT 1
    """)
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def analyze_performance(metrics):
    """Compare metrics to targets and provide recommendations."""
    cagr = metrics.get("cagr_pct", 0)
    sharpe = metrics.get("sharpe_ratio", 0)
    max_dd = metrics.get("max_drawdown_pct", 0)
    trades = metrics.get("total_trades", 0)

    status = []
    recommendations = []

    if trades == 0:
        status.append("❌ NO TRADES - strategy is inactive")
        recommendations.append("CRITICAL: Relax entry filters (lower RSI threshold, remove SMA10, or add news sentiment)")
    else:
        if cagr >= TARGET_CAGR:
            status.append(f"✅ CAGR above target: {cagr:.1f}% >= {TARGET_CAGR}%")
        else:
            status.append(f"⚠️ CAGR below target: {cagr:.1f}% < {TARGET_CAGR}%")
        
        if sharpe >= TARGET_SHARPE:
            status.append(f"✅ Sharpe acceptable: {sharpe:.2f} >= {TARGET_SHARPE}")
        else:
            status.append(f"⚠️ Sharpe low: {sharpe:.2f} < {TARGET_SHARPE}")
            recommendations.append("Improve risk-adjusted returns: add trend filter or increase take-profit ratios")

        if max_dd > TARGET_MAX_DD:
            status.append(f"❌ Drawdown excessive: {max_dd:.1f}% > {TARGET_MAX_DD}%")
            recommendations.append("Reduce position size or add stop-loss tightening")
        else:
            status.append(f"✅ Drawdown within limit: {max_dd:.1f}%")

    return {
        "status": status,
        "recommendations": recommendations,
        "metrics": metrics
    }

def log_progress(analysis):
    """Append analysis to progress log."""
    PROGRESS_LOG.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(PROGRESS_LOG, "a") as f:
        f.write(f"\n## {timestamp}\n\n")
        f.write("### Latest Backtest Results\n")
        f.write(json.dumps(analysis["metrics"], indent=2) + "\n\n")
        f.write("### Assessment\n")
        for s in analysis["status"]:
            f.write(f"- {s}\n")
        if analysis["recommendations"]:
            f.write("\n### Recommended Actions\n")
            for r in analysis["recommendations"]:
                f.write(f"- {r}\n")
        f.write("\n---\n")

def main():
    latest = get_latest_backtest()
    if not latest:
        print("❌ No backtest data found. Run initial backtest first.")
        log_progress({"status": ["No backtest data"], "recommendations": ["Run backtest with current strategy"], "metrics": {}})
        return
    
    metrics = {
        "total_return_pct": latest["total_return_pct"],
        "cagr_pct": latest["cagr_pct"],
        "sharpe_ratio": latest["sharpe_ratio"],
        "max_drawdown_pct": latest["max_drawdown_pct"],
        "total_trades": latest["total_trades"],
        "final_value": latest["final_equity"],
        "run_date": latest.get("created_at") or f"{latest['start_date']} to {latest['end_date']}"
    }
    
    analysis = analyze_performance(metrics)
    print("\n=== Progress Report ===")
    print(f"Backtest: {metrics['run_date']}")
    for s in analysis["status"]:
        print(s)
    if analysis["recommendations"]:
        print("\nNext steps:")
        for r in analysis["recommendations"]:
            print(f"  • {r}")
    else:
        print("\n✅ Strategy on track for target returns.")
    
    log_progress(analysis)

if __name__ == "__main__":
    main()
