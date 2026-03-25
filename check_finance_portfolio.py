#!/usr/bin/env python3
import sqlite3
import json

def check_finance_portfolio(db_path):
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        result = {}

        # List tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        result["tables"] = tables

        # Check positions
        if 'positions' in tables:
            cursor.execute("SELECT COUNT(*) FROM positions;")
            result["positions_count"] = cursor.fetchone()[0]
            if result["positions_count"] > 0:
                cursor.execute("SELECT * FROM positions LIMIT 3;")
                result["positions_sample"] = [dict(row) for row in cursor.fetchall()]

        # Check cash
        if 'cash' in tables:
            cursor.execute("SELECT * FROM cash ORDER BY timestamp DESC LIMIT 1;")
            row = cursor.fetchone()
            if row:
                result["cash"] = dict(row)

        # Check portfolio_snapshots
        if 'portfolio_snapshots' in tables:
            cursor.execute("SELECT * FROM portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 1;")
            row = cursor.fetchone()
            if row:
                result["latest_snapshot"] = dict(row)

        # Check trades
        if 'trades' in tables:
            cursor.execute("SELECT COUNT(*) FROM trades;")
            result["trades_count"] = cursor.fetchone()[0]
            if result["trades_count"] > 0:
                cursor.execute("SELECT * FROM trades ORDER BY timestamp DESC LIMIT 3;")
                result["trades_sample"] = [dict(row) for row in cursor.fetchall()]

        conn.close()
        return result
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    data = check_finance_portfolio("/home/eric/.openclaw/workspace/AITradeAgent/finance_service/storage/portfolio.sqlite")
    print(json.dumps(data, indent=2, default=str))
