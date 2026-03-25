#!/usr/bin/env python3
import sqlite3
from datetime import datetime

def check_analysis_cache(db_path):
    """Check recent analysis cache entries."""
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM analysis_cache;")
        count = cursor.fetchone()[0]

        result = {
            "total_entries": count,
            "latest_entries": []
        }

        if count > 0:
            cursor.execute("""
                SELECT * FROM analysis_cache
                ORDER BY created_at DESC
                LIMIT 5
            """)
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            result["latest_entries"] = [dict(zip(columns, row)) for row in rows]

            # Also get unique symbols
            cursor.execute("SELECT DISTINCT symbol FROM analysis_cache;")
            symbols = [row[0] for row in cursor.fetchall()]
            result["unique_symbols"] = symbols

        conn.close()
        return result
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    data = check_analysis_cache("/home/eric/.openclaw/workspace/AITradeAgent/storage/portfolio.sqlite")
    print(f"Analysis cache status: {data}")
