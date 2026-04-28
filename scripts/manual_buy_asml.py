#!/usr/bin/env python3
"""
Manually execute a BUY for ASML as if it occurred on 2026-03-25.
This fills the missed trade due to earlier bug.
"""

import sys
sys.path.insert(0, '.')

from finance_service.portfolio.trade_repository import TradeRepository
from finance_service.portfolio.models import TradeStatus
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    # Load repository (connects to portfolio.sqlite)
    repo = TradeRepository(use_db=True)
    print(f"Loaded repository: {len(repo.trades)} trades, positions: {list(repo.positions.keys())}")
    
    # Compute quantity based on risk parameters
    # Configuration: sma20_trend strategy: risk_budget_pct=1.5%
    initial_cash = 100000.0  # from config
    # Compute current equity: cash + positions market value
    # For simplicity, use initial_cash as proxy if no positions, but we can compute from repo
    # Calculate current cash as initial_cash - cost_basis(long positions)
    # repo.calculate_portfolio not directly accessible? It's a method of repository. Yes, repo.calculate_portfolio(initial_cash) returns Portfolio.
    portfolio = repo.calculate_portfolio(initial_cash)
    total_equity = portfolio.total_equity()
    print(f"Current total equity (from repo): {total_equity:.2f}")
    
    risk_budget_pct = 0.015  # 1.5%
    risk_amount = total_equity * risk_budget_pct
    print(f"Risk amount: {risk_amount:.2f}")
    
    # ATR from yesterday's data (we already computed): 58.14784034580917
    atr = 58.14784034580917
    risk_per_share = atr * 2
    quantity = int(risk_amount / risk_per_share)
    # Also cap at 20% of cash
    max_by_cash = int(portfolio.current_cash * 0.20 / 1399.42) if portfolio.current_cash > 0 else 0
    quantity = min(quantity, max_by_cash)
    quantity = max(1, quantity)  # at least 1
    print(f"Calculated quantity: {quantity} (risk_per_share={risk_per_share:.2f}, cash limit={max_by_cash})")
    
    # Constants
    symbol = "ASML"
    price = 1399.42
    task_id = f"MANUAL_ASML_20260325"
    now = datetime.utcnow()
    # We'll set ordered_at and filled_at to yesterday around market close: 2025-03-25 16:00 ET? but we'll use UTC.
    # For simplicity, use now.
    
    # Create trade
    trade = repo.create_trade(
        task_id=task_id,
        symbol=symbol,
        side="BUY",
        quantity=quantity,
        price=price,
        decision={
            "confidence": 1.0,
            "rules": ["price_above_sma20"],
            "reason": "Manual fill of missed sma20_trend signal from 2026-03-25"
        },
        confidence=1.0,
        reason="Manual fill of missed signal",
        stop_loss=price - 2 * atr,
        take_profit=price + 3 * atr,
        approval_required=False
    )
    print(f"Created trade: {trade.trade_id}")
    
    # Update position (BUY)
    position = repo.get_position(symbol)
    if position:
        # Existing position: update avg cost and quantity
        old_qty = position.quantity
        old_cost = position.avg_cost
        new_qty = old_qty + quantity
        new_cost = (old_cost * old_qty + price * quantity) / new_qty
        repo.update_position(symbol, quantity=new_qty, avg_cost=new_cost, add_trade=trade.trade_id)
        print(f"Updated existing position: {symbol} qty={new_qty}, avg_cost={new_cost:.2f}")
    else:
        # New position
        repo.create_position(symbol, quantity=quantity, avg_cost=price, trades=[trade.trade_id])
        print(f"Created new position: {symbol} qty={quantity}, avg_cost={price:.2f}")
    
    # Mark trade as filled
    repo.update_trade_status(trade.trade_id, TradeStatus.FILLED, filled_quantity=quantity, executed_by="manual")
    print("Trade marked as FILLED.")
    
    # Show updated portfolio state
    new_portfolio = repo.calculate_portfolio(initial_cash)
    print(f"\nNew portfolio equity: {new_portfolio.total_equity():.2f} (cash: {new_portfolio.current_cash:.2f})")
    print(f"Positions: {[(s, p.quantity, p.avg_cost) for s, p in repo.positions.items()]}")
    
    logger.info("Manual ASML buy execution completed.")

if __name__ == "__main__":
    main()
