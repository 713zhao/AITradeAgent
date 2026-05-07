#!/usr/bin/env python3
import sqlite3
import json
from datetime import datetime

def get_latest_backtest(db_path):
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM backtest_runs
            ORDER BY created_at DESC
            LIMIT 1
        """)
        row = cursor.fetchone()
        if row:
            result = dict(row)
            # Parse JSON fields if present
            if result.get('config_json'):
                result['config'] = json.loads(result['config_json'])
            if result.get('results_json'):
                result['results'] = json.loads(result['results_json'])
            # Remove raw JSON strings to avoid duplication
            result.pop('config_json', None)
            result.pop('results_json', None)
            return result
        else:
            return None
    except Exception as e:
        return {"error": str(e)}
    finally:
        if 'conn' in locals():
            conn.close()

def get_backtest_summary(db_path):
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM backtest_runs;")
        total = cursor.fetchone()[0]

        cursor.execute("SELECT MAX(created_at) FROM backtest_runs;")
        latest_date = cursor.fetchone()[0]

        cursor.execute("SELECT AVG(total_return_pct), AVG(sharpe_ratio), AVG(max_drawdown_pct) FROM backtest_runs;")
        avg_return, avg_sharpe, avg_drawdown = cursor.fetchone()

        conn.close()
        return {
            "total_backtests": total,
            "latest_backtest_date": latest_date,
            "average_return_pct": avg_return,
            "average_sharpe_ratio": avg_sharpe,
            "average_max_drawdown_pct": avg_drawdown
        }
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    db_path = "/home/eric/.openclaw/workspace/AITradeAgent/finance_service/storage/backtest.sqlite"

    print("=== LATEST BACKTEST ===")
    latest = get_latest_backtest(db_path)
    if latest:
        print(json.dumps(latest, indent=2, default=str))
    else:
        print("No backtest found")

    print("\n=== BACKTEST SUMMARY ===")
    summary = get_backtest_summary(db_path)
    print(json.dumps(summary, indent=2, default=str))
