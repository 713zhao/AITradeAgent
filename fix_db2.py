import sqlite3
import json

conn = sqlite3.connect("finance_service/storage/portfolio.sqlite")
cur = conn.cursor()

cur.execute("SELECT trade_id, data FROM trade_store")
rows = cur.fetchall()

for trade_id, data_str in rows:
    data = json.loads(data_str)
    if data["status"] == "filled" and data["filled_quantity"] > data["quantity"]:
        print(f"ERROR: {data['trade_id']} filled qty ({data['filled_quantity']}) still > qty ({data['quantity']})")
print("Check done")
