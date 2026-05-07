#!/usr/bin/env python3
import sqlite3

def show_tables_info(db_path):
    """Show structure of all relevant tables."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        tables = ["positions", "trades", "portfolio_snapshots", "config_audit_log", "analysis_cache"]
        for table in tables:
            print(f"\n=== {table} ===")
            try:
                cursor.execute(f"PRAGMA table_info({table});")
                columns = cursor.fetchall()
                print("Columns:")
                for col in columns:
                    print(f"  {col[1]} ({col[2]})")

                cursor.execute(f"SELECT COUNT(*) FROM {table};")
                count = cursor.fetchone()[0]
                print(f"Rows: {count}")

                if count > 0:
                    cursor.execute(f"SELECT * FROM {table} LIMIT 2;")
                    rows = cursor.fetchall()
                    for row in rows:
                        print(f"  Sample: {row}")
            except Exception as e:
                print(f"  Error: {e}")

        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    show_tables_info("/home/eric/.openclaw/workspace/AITradeAgent/storage/portfolio.sqlite")
