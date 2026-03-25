#!/usr/bin/env python3
import sqlite3
import json
from datetime import datetime

def get_portfolio_status(db_path):
    """Query the portfolio database for current status."""
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Check if portfolio table exists and get its structure
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]

        portfolio_data = {
            "timestamp": datetime.now().isoformat(),
            "tables_found": tables,
            "positions": [],
            "cash": None,
            "total_value": None,
            "realized_pnl": None,
            "unrealized_pnl": None
        }

        # Query portfolio positions if table exists
        if 'portfolio' in tables:
            cursor.execute("PRAGMA table_info(portfolio);")
            columns = [row[1] for row in cursor.fetchall()]
            portfolio_data["portfolio_columns"] = columns

            cursor.execute("SELECT * FROM portfolio;")
            rows = cursor.fetchall()
            positions = []
            for row in rows:
                pos = dict(zip(columns, row))
                positions.append(pos)
            portfolio_data["positions"] = positions

        # Get cash balance if cash table exists
        if 'cash' in tables:
            cursor.execute("SELECT * FROM cash ORDER BY timestamp DESC LIMIT 1;")
            cash_row = cursor.fetchone()
            if cash_row:
                cash_columns = [desc[0] for desc in cursor.description]
                portfolio_data["cash"] = dict(zip(cash_columns, cash_row))

        # Get P&L if pnl table exists
        if 'pnl' in tables:
            cursor.execute("SELECT * FROM pnl ORDER BY date DESC LIMIT 1;")
            pnl_row = cursor.fetchone()
            if pnl_row:
                pnl_columns = [desc[0] for desc in cursor.description]
                portfolio_data["pnl"] = dict(zip(pnl_columns, pnl_row))

        conn.close()
        return portfolio_data

    except Exception as e:
        return {"error": str(e)}

def check_cache_status(cache_path):
    """Check the cache database for recent activity."""
    try:
        conn = sqlite3.connect(cache_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]

        cache_data = {
            "tables": tables,
            "last_updated": None
        }

        # Try to find any table with timestamp
        for table in tables:
            try:
                cursor.execute(f"SELECT MAX(timestamp) as max_ts FROM {table};")
                result = cursor.fetchone()
                if result and result[0]:
                    cache_data["last_updated"] = result[0]
                    break
            except:
                continue

        conn.close()
        return cache_data
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    portfolio_db = "/home/eric/.openclaw/workspace/AITradeAgent/storage/portfolio.sqlite"
    cache_db = "/home/eric/.openclaw/workspace/AITradeAgent/storage/cache.sqlite"

    print("=== PORTFOLIO STATUS ===")
    portfolio = get_portfolio_status(portfolio_db)
    print(json.dumps(portfolio, indent=2, default=str))

    print("\n=== CACHE STATUS ===")
    cache = check_cache_status(cache_db)
    print(json.dumps(cache, indent=2, default=str))
