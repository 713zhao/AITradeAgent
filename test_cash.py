import asyncio
from finance_service.portfolio.trade_repository import TradeRepository
from finance_service.portfolio.models import TradeStatus

async def main():
    repo = TradeRepository(use_db=False)
    # Buy 10 AAPL @ 100
    t1 = repo.create_trade("t1", "AAPL", "BUY", 10, 100.0, {}, 1.0)
    repo.create_position("AAPL", 10, 100.0, [t1.trade_id])
    repo.update_trade_status(t1.trade_id, TradeStatus.FILLED, 10)
    
    # Sell 5 AAPL @ 150
    t2 = repo.create_trade("t2", "AAPL", "SELL", 5, 150.0, {}, 1.0)
    repo.update_position("AAPL", quantity=5)
    repo.update_trade_status(t2.trade_id, TradeStatus.FILLED, 5)
    
    # Current AAPL price = 150
    repo.update_position("AAPL", current_price=150.0)
    
    # Calculate
    portfolio = repo.calculate_portfolio(10000.0)
    print("Initial cash:", portfolio.initial_cash)
    print("Current cash:", portfolio.current_cash)
    print("Positions value:", portfolio.net_position_value())
    print("Equity:", portfolio.total_equity())
    print("Total PnL:", portfolio.total_pnl())
    print("Realized:", portfolio.realized_pnl())
    print("Unrealized:", portfolio.unrealized_pnl())

asyncio.run(main())
