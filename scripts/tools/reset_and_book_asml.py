#!/usr/bin/env python3
"""
Reset portfolio to initial cash and manually book ASML buy for 2026-03-25.
"""

import sys
sys.path.insert(0, '.')

from finance_service.portfolio.trade_repository import TradeRepository
from finance_service.portfolio.models import TradeStatus, Position
from finance_service.core.yaml_config import YAMLConfigEngine
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    # Load config for initial cash
    config = YAMLConfigEngine('config')
    initial_cash = config.get("finance", "portfolio/initial_cash", default=100000.0)
    print(f"Initial cash from config: ${initial_cash:,.2f}")
    
    # Fresh repository (will create new portfolio.sqlite)
    repo = TradeRepository(use_db=True)
    print(f"Fresh repository loaded: {len(repo.trades)} trades, {len(repo.positions)} positions")
    
    # Yesterday's data for ASML
    trade_date = datetime.strptime('2026-03-25', '%Y-%m-%d')
    price = 1399.42
    atr = 58.14784034580917  # from earlier calculation
    risk_budget_pct = 0.015   # 1.5% from config (strategy default)
    
    # Compute position size
    total_equity = initial_cash  # Starting fresh
    risk_amount = total_equity * risk_budget_pct
    risk_per_share = atr * 2
    quantity = int(risk_amount / risk_per_share)
    # Cap at 20% of cash
    max_cash_qty = int(initial_cash * 0.20 / price)
    quantity = min(quantity, max_cash_qty)
    quantity = max(1, quantity)
    
    print(f"Position size: {quantity} shares")
    print(f"Risk per share: ${risk_per_share:.2f}, Total risk: ${risk_amount:.2f}")
    
    # Create BUY trade
    task_id = f"ASML_20260325_MANUAL"
    trade = repo.create_trade(
        task_id=task_id,
        symbol="ASML",
        side="BUY",
        quantity=quantity,
        price=price,
        decision={
            "confidence": 1.0,
            "rules": ["price_above_sma20"],
            "reason": "sma20_trend signal from 2026-03-25 (manual fill after bug fix)"
        },
        confidence=1.0,
        reason="Manual fill of missed signal",
        stop_loss=price - 2 * atr,
        take_profit=price + 3 * atr,
        approval_required=False
    )
    print(f"Created trade: {trade.trade_id}")
    
    # Update position (BUY) with current_price
    repo.create_position(
        symbol="ASML",
        quantity=quantity,
        avg_cost=price,
        trades=[trade.trade_id]
    )
    # Set current_price to latest price
    repo.update_position(symbol="ASML", current_price=price)
    print(f"Created position: ASML qty={quantity}, avg_cost={price:.2f}, current_price={price:.2f}")
    
    # Mark trade as filled
    repo.update_trade_status(trade.trade_id, TradeStatus.FILLED, filled_quantity=quantity, executed_by="manual")
    print("Trade marked FILLED")
    
    # Verify portfolio state
    portfolio = repo.calculate_portfolio(initial_cash)
    print(f"\nPortfolio after ASML buy:")
    print(f"  Total equity: ${portfolio.total_equity():,.2f}")
    print(f"  Cash: ${portfolio.current_cash:,.2f}")
    print(f"  Positions: {[(s, p.quantity, p.avg_cost) for s, p in repo.positions.items()]}")
    
    logger.info("Portfolio reset and ASML buy completed successfully.")

if __name__ == "__main__":
    main()
