"""Test portfolio simulation"""
import sys
import json

def test_portfolio():
    """Test portfolio operations"""
    print(f"\n{'='*60}")
    print("Testing Portfolio Simulation")
    print(f"{'='*60}\n")
    
    sys.path.insert(0, str(__file__).rsplit('/', 2)[0])
    
    from finance_service.sim.portfolio import Portfolio
    from finance_service.sim.metrics import Metrics
    
    # Create portfolio
    portfolio = Portfolio(initial_cash=100000)
    print(f"Initial State:")
    print(json.dumps(portfolio.get_state(), indent=2))
    
    # Simulate some trades
    print(f"\n{'='*60}\nExecuting Trades\n{'='*60}\n")
    
    # Trade 1: Buy AAPL
    success, msg = portfolio.buy("AAPL", 10, 150.0)
    print(f"1. {msg}")
    print(json.dumps(portfolio.get_state(), indent=2))
    
    # Trade 2: Buy TSLA
    success, msg = portfolio.buy("TSLA", 5, 200.0)
    print(f"\n2. {msg}")
    print(json.dumps(portfolio.get_state(), indent=2))
    
    # Trade 3: Price update (mark to market)
    prices = {"AAPL": 155.0, "TSLA": 210.0}
    portfolio.update_prices(prices)
    portfolio.snapshot()
    print(f"\n3. Updated prices: {prices}")
    print(json.dumps(portfolio.get_state(), indent=2))
    
    # Trade 4: Sell AAPL
    success, msg = portfolio.sell("AAPL", 5, 155.0)
    print(f"\n4. {msg}")
    print(json.dumps(portfolio.get_state(), indent=2))
    
    # Display metrics
    print(f"\n{'='*60}\nPerformance Metrics\n{'='*60}\n")
    metrics = Metrics.summary(portfolio)
    
    print("Portfolio State:")
    state = metrics['portfolio']
    print(f"  Cash: ${state['cash']:.2f}")
    print(f"  Equity: ${state['equity']:.2f}")
    print(f"  Total Value: ${state['total_value']:.2f}")
    print(f"  Total PnL: ${state['total_pnl']:.2f} ({state['pnl_pct']:.2f}%)")
    
    print("\nReturns:")
    returns = metrics['returns']
    print(f"  Total Return: {returns['total_return_pct']:.2f}%")
    print(f"  CAGR: {returns['cagr']:.2f}%")
    print(f"  Volatility: {returns['volatility']:.2f}%")
    
    print("\nRisk:")
    dd = metrics['drawdown']
    print(f"  Max Drawdown: {dd['max_drawdown_pct']:.2f}%")
    print(f"  Current Drawdown: {dd['current_drawdown_pct']:.2f}%")
    
    print("\nSharpe Ratio:")
    sharpe = metrics['sharpe']
    print(f"  {sharpe['sharpe_ratio']:.2f}")
    
    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    test_portfolio()
