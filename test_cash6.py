import asyncio
from finance_service.portfolio.trade_repository import TradeRepository

repo = TradeRepository(use_db=True)
p = repo.calculate_portfolio(100000.0)
print("Initial Cash:", p.initial_cash)
print("Current Cash:", p.current_cash)
print("Net Position Value:", p.net_position_value())
print("Total Equity:", p.total_equity())
print("Realized PnL:", p.realized_pnl())
print("Total PnL:", p.total_pnl())
