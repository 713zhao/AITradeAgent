import asyncio
from finance_service.portfolio.trade_repository import TradeRepository
from finance_service.storage import get_portfolio_db

repo = TradeRepository(use_db=True)
p = repo.calculate_portfolio(100000.0)
print(p.current_cash)
for pos in p.positions.values():
    print(pos.symbol, pos.quantity, pos.avg_cost)
print("Trades:")
for t in p.trades:
    print(t.symbol, t.side, t.quantity, t.price, t.status)
