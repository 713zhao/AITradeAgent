"""Decision generation from indicators and rules"""
from dataclasses import dataclass, asdict
from typing import Dict, List, Tuple, Optional
import pandas as pd
from finance_service.core.models import Decision
from finance_service.indicators.models import SignalType
import logging

logger = logging.getLogger(__name__)


@dataclass
class DecisionContext:
    """Context for decision making"""
    symbol: str
    current_price: float
    atr: float  # For stop loss / take profit sizing
    entry_triggered: bool
    entry_confidence: float
    entry_rules: List[str]
    exit_triggered: bool
    exit_rules: List[str]
    all_signals: Dict[str, SignalType]


class DecisionEngine:
    """
    Converts indicators + rules into trading decisions
    
    Output: Decision JSON with symbol, decision, confidence, SL/TP
    """
    
    def __init__(self, atr_multiplier_sl: float = 2.0, atr_multiplier_tp: float = 3.0):
        """
        Initialize DecisionEngine
        
        Args:
            atr_multiplier_sl: Stop loss distance = current_price - (atr * multiplier)
            atr_multiplier_tp: Take profit distance = current_price + (atr * multiplier)
        """
        self.atr_multiplier_sl = atr_multiplier_sl
        self.atr_multiplier_tp = atr_multiplier_tp
        logger.info(f"DecisionEngine initialized: SL={atr_multiplier_sl}x ATR, TP={atr_multiplier_tp}x ATR")
    
    def make_decision(self, context: DecisionContext) -> Decision:
        """
        Generate trading decision from context
        
        Args:
            context: DecisionContext with all indicators and rules evaluated
        
        Returns:
            Decision: Trading decision with symbol, action, confidence, SL/TP
        """
        
        # Determine decision based on rule evaluation
        if context.exit_triggered:
            decision = "SELL"
            confidence = 0.7  # Exit decisions are less precise
            signals = context.exit_rules
        elif context.entry_triggered:
            decision = "BUY"
            confidence = context.entry_confidence
            signals = context.entry_rules
        else:
            decision = "HOLD"
            confidence = 0.0
            signals = []
        
        # Calculate stop loss and take profit
        stop_loss, take_profit = self._calculate_sl_tp(
            context.current_price,
            context.atr,
            decision
        )
        
        # Build Decision object
        dec = Decision(
            symbol=context.symbol,
            decision=decision,
            confidence=min(confidence, 1.0),  # Cap at 1.0
            signals=signals,
            stop_loss=stop_loss,
            take_profit=take_profit,
            timestamp=pd.Timestamp.now()
        )
        
        logger.info(f"Decision: {context.symbol} → {decision} (conf: {confidence:.2%}, SL: {stop_loss}, TP: {take_profit})")
        
        return dec
    
    def _calculate_sl_tp(self, price: float, atr: float, decision: str) -> Tuple[Optional[float], Optional[float]]:
        """
        Calculate stop loss and take profit levels
        
        Args:
            price: Current price
            atr: Average True Range value
            decision: BUY, SELL, or HOLD
        
        Returns:
            Tuple of (stop_loss, take_profit) prices
        """
        if decision == "BUY":
            # For long: SL below, TP above
            sl = price - (atr * self.atr_multiplier_sl)
            tp = price + (atr * self.atr_multiplier_tp)
        elif decision == "SELL":
            # For short: SL above, TP below
            sl = price + (atr * self.atr_multiplier_sl)
            tp = price - (atr * self.atr_multiplier_tp)
        else:
            # HOLD: no SL/TP
            sl = None
            tp = None
        
        # Round to 2 decimals for prices
        if sl:
            sl = round(sl, 2)
        if tp:
            tp = round(tp, 2)
        
        return sl, tp
