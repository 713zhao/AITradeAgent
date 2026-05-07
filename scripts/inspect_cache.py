#!/usr/bin/env python3
import sqlite3

def inspect_cache_db(db_path):
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]

        print(f"Cache DB: {db_path}")
        print(f"Tables: {tables}\n")

        for table in tables:
            print(f"=== {table} ===")
            cursor.execute(f"PRAGMA table_info({table});")
            cols = [row[1] for row in cursor.fetchall()]
            print(f"Columns: {cols}")
            cursor.execute(f"SELECT COUNT(*) FROM {table};")
            cnt = cursor.fetchone()[0]
            print(f"Rows: {cnt}")
            if cnt > 0:
                cursor.execute(f"SELECT * FROM {table} ORDER BY ROWID DESC LIMIT 2;")
                for row in cursor.fetchall():
                    print(f"  {row}")
            print()
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    inspect_cache_db("/home/eric/.openclaw/workspace/AITradeAgent/storage/cache.sqlite")
