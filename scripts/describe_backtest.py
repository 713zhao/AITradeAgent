#!/usr/bin/env python3
import sqlite3

def describe_backtest_table(db_path):
    """Show structure of backtest_runs table."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(backtest_runs);")
        columns = cursor.fetchall()

        print("=== backtest_runs table structure ===")
        for col in columns:
            print(f"  {col[1]} ({col[2]})")

        # Show all data
        cursor.execute("SELECT * FROM backtest_runs;")
        rows = cursor.fetchall()
        print(f"\n=== Data ({len(rows)} rows) ===")
        for row in rows:
            print(row)

        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    describe_backtest_table("/home/eric/.openclaw/workspace/AITradeAgent/storage/portfolio.sqlite")
