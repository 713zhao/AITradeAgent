import asyncio
from finance_service.portfolio.trade_repository import TradeRepository
from finance_service.portfolio.models import Portfolio

def compute_pnl(initial_cash: float):
    repo = TradeRepository(use_db=True)
    p = repo.calculate_portfolio(initial_cash)
    print("Equity:", p.total_equity())
    print("Total PNL:", p.total_pnl())
    print("Realized PNL:", p.realized_pnl())
    print("Unrealized PNL:", p.unrealized_pnl())

compute_pnl(100000.0)
