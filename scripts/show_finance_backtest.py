#!/usr/bin/env python3
import sqlite3

def show_backtest_db_contents(db_path):
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Get tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]

        print(f"Database: {db_path}")
        print(f"Tables: {tables}\n")

        for table in tables:
            print(f"=== {table} ===")
            cursor.execute(f"PRAGMA table_info({table});")
            columns = [row[1] for row in cursor.fetchall()]
            print(f"Columns: {columns}")

            cursor.execute(f"SELECT COUNT(*) FROM {table};")
            count = cursor.fetchone()[0]
            print(f"Rows: {count}")

            if count > 0:
                cursor.execute(f"SELECT * FROM {table} LIMIT 3;")
                rows = cursor.fetchall()
                for row in rows:
                    print(f"  {row}")
            print()

        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    show_backtest_db_contents("/home/eric/.openclaw/workspace/AITradeAgent/finance_service/storage/backtest.sqlite")
