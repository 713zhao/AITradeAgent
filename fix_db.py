import sqlite3
import json

conn = sqlite3.connect("finance_service/storage/portfolio.sqlite")
cur = conn.cursor()

cur.execute("SELECT trade_id, data FROM trade_store")
rows = cur.fetchall()

fixed = 0
for trade_id, data_str in rows:
    data = json.loads(data_str)
    # The previous fix assigned filled_quantity = quantity
    # We saw filled_quantity was like 237 for a 68 quantity order.
    # The bug was likely setting the quantity of the position into the filled_quantity of the trade.
    # The previous fix I did was right to set it back to data['quantity'].
    # Wait, in the output of test_cash4.py, the total value was correct, leading to a cash balance of -920.796
    pass

