from finance_service.portfolio.models import Position, Trade, TradeStatus

def calculate_cash(initial_cash, trades):
    current_cash = initial_cash
    for trade in trades:
        if trade.status == TradeStatus.FILLED:
            trade_val = (trade.filled_quantity * trade.price) / Position._fx(trade.symbol)
            if trade.side == "BUY":
                current_cash -= trade_val
            elif trade.side == "SELL":
                current_cash += trade_val
    return current_cash

t1 = Trade("t1", "", "AAPL", "BUY", 10, 100, TradeStatus.FILLED, 10)
t2 = Trade("t2", "", "AAPL", "SELL", 5, 150, TradeStatus.FILLED, 5)

print(calculate_cash(10000, [t1, t2]))
