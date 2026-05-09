import asyncio
from finance_service.core.config import Config
from finance_service.agents.data_agent import DataAgent
from finance_service.agents.market_scanner_agent import MarketScannerAgent
from finance_service.portfolio.trade_repository import TradeRepository

async def main():
    config = Config()
    data_agent = DataAgent(config)
    repo = TradeRepository(use_db=True)
    
    held = [p.symbol for p in repo.get_positions()]
    print("Held:", held)
    scanner = MarketScannerAgent(config)
    
    print("Refreshing prices...")
    report = await scanner.refresh_watchlist_prices(data_agent=data_agent, held_symbols=held, force_held=True)
    if report and report.status == "success":
        prices = {item["symbol"]: item["price"] for item in report.payload.get("prices", [])}
        print("Fetched prices:", prices)
        repo.update_position_prices(prices)
        print("Portfolio DB updated!")
    else:
        print("Failed to fetch.")

asyncio.run(main())
