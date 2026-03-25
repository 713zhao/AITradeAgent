#!/usr/bin/env python3
import sqlite3
import json
from datetime import datetime

def check_backtest_results(db_path):
    """Query backtest results from cache or portfolio database."""
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Check if backtest_runs table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='backtest_runs';")
        if not cursor.fetchone():
            return {"error": "backtest_runs table not found"}

        # Get the most recent backtest run
        cursor.execute("""
            SELECT * FROM backtest_runs
            ORDER BY started_at DESC
            LIMIT 1
        """)
        row = cursor.fetchone()
        if row:
            columns = [desc[0] for desc in cursor.description]
            backtest_data = dict(zip(columns, row))

            # Also get performance metrics if available
            cursor.execute("PRAGMA table_info(backtest_runs);")
            all_columns = [row[1] for row in cursor.fetchall()]
            return {
                "latest_backtest": backtest_data,
                "all_columns": all_columns
            }
        else:
            return {"message": "No backtest runs found"}
    except Exception as e:
        return {"error": str(e)}
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    db_path = "/home/eric/.openclaw/workspace/AITradeAgent/storage/portfolio.sqlite"
    results = check_backtest_results(db_path)
    print(json.dumps(results, indent=2, default=str))
