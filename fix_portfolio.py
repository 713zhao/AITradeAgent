import re
with open("finance_service/agents/portfolio_agent.py", "r") as f:
    text = f.read()

old_reason = """        take_profit = trade_info.get("take_profit")
        trade_id = trade_info.get("trade_id") or f"exec_{int(datetime.utcnow().timestamp()*1000)}\""""
new_reason = """        take_profit = trade_info.get("take_profit")
        reason = trade_info.get("reason", "Executed Trade")
        trade_id = trade_info.get("trade_id") or f"exec_{int(datetime.utcnow().timestamp()*1000)}\""""
text = text.replace(old_reason, new_reason)

old_buy = """                    decision={}, confidence=1.0, reason="Executed Trade","""
new_buy = """                    decision={}, confidence=1.0, reason=reason,"""
text = text.replace(old_buy, new_buy, 1)

old_sell = """            elif side == "SELL":
                logger.info(f"[PORTFOLIO DEBUG] Creating SELL trade for {symbol}")
                trade = self.repository.create_trade(
                    task_id=trade_id,
                    symbol=symbol, side="SELL", quantity=quantity, price=price,
                    decision={}, confidence=1.0, reason="Executed Trade",
                    stop_loss=stop_loss, take_profit=take_profit
                )
                position = self.repository.get_position(symbol)
                if position:
                    new_qty = position.quantity - quantity
                    if new_qty == 0:
                        self.repository.close_position(symbol)
                    else:
                        self.repository.update_position(symbol, quantity=new_qty, add_trade=trade_id)
                        # Also update current_price to latest (execution price) for transparency
                        self.repository.update_position(symbol, current_price=price)
                else:
                    # Short sale
                    self.repository.create_position(symbol, quantity=-quantity, avg_cost=price, trades=[trade_id])"""

new_sell = """            elif side == "SELL":
                logger.info(f"[PORTFOLIO DEBUG] Creating SELL trade for {symbol}")
                
                # Fetch position before selling to calculate PnL and hold time for the notification
                position = self.repository.get_position(symbol)
                realized_pnl = 0.0
                pnl_pct = 0.0
                hold_days = 0
                if position:
                    realized_pnl = (price - position.avg_cost) * quantity
                    pnl_pct = ((price - position.avg_cost) / position.avg_cost) * 100 if position.avg_cost > 0 else 0
                    
                    # Calculate holding period if trades exist
                    if position.trades:
                        first_trade_id = position.trades[0]
                        first_trade = self.repository.get_trade(first_trade_id)
                        if first_trade and first_trade.filled_at:
                            hold_time = datetime.utcnow() - first_trade.filled_at
                            hold_days = hold_time.days
                
                trade = self.repository.create_trade(
                    task_id=trade_id,
                    symbol=symbol, side="SELL", quantity=quantity, price=price,
                    decision={}, confidence=1.0, reason=reason,
                    stop_loss=stop_loss, take_profit=take_profit
                )
                
                # Store calculated PnL in trade_info for HealthAgent to use
                trade_info['realized_pnl'] = realized_pnl
                trade_info['pnl_pct'] = pnl_pct
                trade_info['hold_days'] = hold_days
                
                if position:
                    new_qty = position.quantity - quantity
                    if new_qty == 0:
                        self.repository.close_position(symbol)
                    else:
                        self.repository.update_position(symbol, quantity=new_qty, add_trade=trade_id)
                        # Also update current_price to latest (execution price) for transparency
                        self.repository.update_position(symbol, current_price=price)
                else:
                    # Short sale
                    self.repository.create_position(symbol, quantity=-quantity, avg_cost=price, trades=[trade_id])"""

text = text.replace(old_sell, new_sell)

with open("finance_service/agents/portfolio_agent.py", "w") as f:
    f.write(text)
print("Patched portfolio agent.")
