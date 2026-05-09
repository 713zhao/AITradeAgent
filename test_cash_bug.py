import asyncio
from finance_service.portfolio.trade_repository import TradeRepository
from finance_service.portfolio.models import Position

repo = TradeRepository(use_db=True)

for trade in repo.trades:
    if trade.status.value == "filled":
        val = (trade.filled_quantity * trade.price) / Position._fx(trade.symbol)
        print(f"Trade: {trade.symbol} {trade.side} qty={trade.filled_quantity} price={trade.price} fx={Position._fx(trade.symbol)} -> val={val}")

