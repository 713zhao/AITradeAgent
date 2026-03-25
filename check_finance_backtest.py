#!/usr/bin/env python3
import sqlite3
import json

def inspect_backtest_db(db_path):
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Get tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]

        result = {"tables": tables, "data": {}}

        for table in tables:
            cursor.execute(f"PRAGMA table_info({table});")
            columns = [row[1] for row in cursor.fetchall()]
            cursor.execute(f"SELECT COUNT(*) FROM {table};")
            count = cursor.fetchone()[0]
            result["data"][table] = {
                "columns": columns,
                "count": count
            }
            if count > 0:
                cursor.execute(f"SELECT * FROM {table} ORDER BY id DESC LIMIT 1;")
                row = cursor.fetchone()
                result["data"][table]["latest"] = dict(zip(columns, row))

        conn.close()
        return result
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    data = inspect_backtest_db("/home/eric/.openclaw/workspace/AITradeAgent/finance_service/storage/backtest.sqlite")
    print(json.dumps(data, indent=2, default=str))
