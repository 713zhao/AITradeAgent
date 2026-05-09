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
        
print("Cash before shorts:", cash)

# Shorts reduce cash available (margin requirement)
short_margin = sum(
    abs(pos.market_value_usd())
    for pos in repo.positions.values()
    if pos.quantity < 0  # Short positions
)
print("Short margin:", short_margin)
cash -= short_margin
print("Final cash:", cash)
