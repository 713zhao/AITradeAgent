"""Trade execution logic"""
import logging
from typing import Dict, Tuple, Optional
from datetime import datetime
from ..core.models import Trade, Decision
from ..tools.risk_tools import RiskTools
from .portfolio import Portfolio

logger = logging.getLogger(__name__)

class Execution:
    """Trade execution and validation"""
    
    def __init__(self, portfolio: Portfolio):
        self.portfolio = portfolio
        self.pending_trades: Dict[str, Trade] = {}
    
    def propose_trade(self, decision: Decision) -> Tuple[bool, str, Dict]:
        """
        Propose a trade based on decision
        
        Returns:
            (valid, message, trade_dict)
        """
        symbol = decision.symbol
        action = decision.decision
        
        if action == "HOLD":
            return False, "HOLD decision: no trade proposed", {}
        
        qty = decision.position.get("action_qty", 0)
        price = decision.position.get("action_value", 0)
        
        if price == 0 or qty == 0:
            return False, "Trade missing quantity or price", {}
        
        # Normalize unit price
        unit_price = price / qty if qty != 0 else 0
        
        # Validate against portfolio and risk policies
        val_result = RiskTools.validate_trade(
            symbol=symbol,
            action=action,
            qty=qty,
            price=unit_price,
            portfolio_equity=self.portfolio.total_value,
            existing_positions=self.portfolio.positions,
        )
        
        if not val_result["valid"]:
            return False, "; ".join(val_result["errors"]), {}
        
        # Create trade object
        trade = Trade(
            task_id=decision.task_id,
            symbol=symbol,
            action=action,
            qty=qty,
            price=unit_price,
            timestamp=datetime.utcnow().isoformat(),
        )
        
        # Store pending
        self.pending_trades[decision.task_id] = trade
        
        summary = f"{action} {qty} {symbol} @ ${unit_price:.2f}"
        if val_result["warnings"]:
            summary += " (Warnings: " + "; ".join(val_result["warnings"]) + ")"
        
        return True, summary, {
            "trade": {
                "task_id": trade.task_id,
                "symbol": trade.symbol,
                "action": trade.action,
                "qty": trade.qty,
                "price": trade.price,
                "timestamp": trade.timestamp,
            },
            "validation": val_result,
        }
    
    def execute_trade(self, task_id: str, approval_id: str = "") -> Tuple[bool, str]:
        """
        Execute a pending trade
        
        Returns:
            (success, message)
        """
        if task_id not in self.pending_trades:
            return False, f"No pending trade for task {task_id}"
        
        trade = self.pending_trades[task_id]
        trade.approval_id = approval_id
        trade.approved = True
        
        if trade.action == "BUY":
            success, msg = self.portfolio.buy(trade.symbol, trade.qty, trade.price)
        elif trade.action == "SELL":
            success, msg = self.portfolio.sell(trade.symbol, trade.qty, trade.price)
        else:
            return False, f"Unknown action: {trade.action}"
        
        if success:
            del self.pending_trades[task_id]
            logger.info(f"Executed trade: {msg}")
        
        return success, msg
    
    def cancel_trade(self, task_id: str) -> Tuple[bool, str]:
        """Cancel a pending trade"""
        if task_id in self.pending_trades:
            del self.pending_trades[task_id]
            return True, f"Cancelled trade {task_id}"
        return False, f"No pending trade {task_id}"
    
    def get_pending(self, task_id: Optional[str] = None) -> Dict:
        """Get pending trades"""
        if task_id:
            return self.pending_trades.get(task_id, {})
        return self.pending_trades
