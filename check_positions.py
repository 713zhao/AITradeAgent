#!/usr/bin/env python3
import sqlite3
import json
from datetime import datetime

def check_positions_and_trades(db_path):
    """Check current positions and recent trades."""
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        result = {
            "positions_count": 0,
            "positions": [],
            "recent_trades": [],
            "portfolio_snapshots": []
        }

        # Check positions
        cursor.execute("SELECT COUNT(*) as count FROM positions;")
        count_row = cursor.fetchone()
        result["positions_count"] = count_row[0] if count_row else 0

        if result["positions_count"] > 0:
            cursor.execute("SELECT * FROM positions ORDER BY symbol;")
            result["positions"] = [dict(row) for row in cursor.fetchall()]

        # Recent trades (limit 10)
        cursor.execute("SELECT * FROM trades ORDER BY trade_date DESC LIMIT 10;")
        trades = cursor.fetchall()
        if trades:
            columns = [desc[0] for desc in cursor.description]
            result["recent_trades"] = [dict(zip(columns, row)) for row in trades]

        # Latest portfolio snapshot
        cursor.execute("SELECT * FROM portfolio_snapshots ORDER BY timestamp DESC LIMIT 1;")
        snapshot = cursor.fetchone()
        if snapshot:
            columns = [desc[0] for desc in cursor.description]
            result["portfolio_snapshots"] = dict(zip(columns, snapshot))

        conn.close()
        return result

    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    data = check_positions_and_trades("/home/eric/.openclaw/workspace/AITradeAgent/storage/portfolio.sqlite")
    print(json.dumps(data, indent=2, default=str))
