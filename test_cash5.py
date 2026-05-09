import asyncio
from finance_service.portfolio.trade_repository import TradeRepository

repo = TradeRepository(use_db=True)
p = repo.calculate_portfolio(100000.0)
spent = sum(
            pos.cost_basis_usd()
            for pos in repo.positions.values()
            if pos.quantity > 0  # Long positions only
        )
print("Old spent calculation:", spent)
print("Old cash calculation:", 100000.0 - spent)
