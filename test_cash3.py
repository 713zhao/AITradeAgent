import asyncio
from finance_service.portfolio.trade_repository import TradeRepository

repo = TradeRepository(use_db=True)
cash = 100000.0
for trade in repo.trades:
    if trade.status.value == "filled":
        from finance_service.portfolio.models import Position
        val = (trade.filled_quantity * trade.price) / Position._fx(trade.symbol)
        if trade.side == "BUY": cash -= val
        elif trade.side == "SELL": cash += val
        print(f"{trade.side} {trade.quantity} {trade.symbol} at {trade.price}. Val: {val}. Cash: {cash}")

print(cash)
