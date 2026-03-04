"""Baseline rule-based strategy"""
import logging
from typing import Dict, Any, List, Optional
from .strategy_interface import StrategyInterface
from ..tools.risk_tools import RiskTools

logger = logging.getLogger(__name__)

class BaselineRuleStrategy(StrategyInterface):
    """
    Simple rule-based strategy combining trend + momentum
    
    Rules:
    - Trend filter: price > SMA(50) for bullish
    - Momentum: RSI(14) 45-70 for buy bias
    - Exit: price < SMA(50) or RSI > 75
    """
    
    def __init__(self):
        super().__init__("baseline_rule")
        self.sma_window = 50
        self.rsi_window = 14
        self.rsi_buy_low = 45
        self.rsi_buy_high = 70
        self.rsi_sell_high = 75
    
    def analyze(self, symbol: str, data: Dict[str, Any],
               portfolio_equity: float = 100000,
               existing_position: Optional[float] = None) -> Dict[str, Any]:
        """
        Analyze symbol using baseline rules
        
        Args:
            symbol: Ticker symbol
            data: Dict with keys containing prices, indicators
            portfolio_equity: Portfolio equity for sizing
            existing_position: Existing qty if any
        
        Returns:
            Decision dict
        """
        # Extract data
        closes = data.get("close", [])
        highs = data.get("high", [])
        lows = data.get("low", [])
        atr_values = data.get("atr", [])
        sma50 = data.get("sma50", [])
        rsi = data.get("rsi", [])
        
        # Need minimum data
        if not closes or len(closes) < self.sma_window:
            return self._create_decision(
                symbol, "HOLD", 0.0,
                {"error": "Insufficient data"},
                ["Not enough data for analysis"]
            )
        
        # Get latest values
        last_close = closes[-1]
        last_high = highs[-1] if highs else last_close
        last_low = lows[-1] if lows else last_close
        last_sma50 = sma50[-1] if sma50 else None
        last_rsi = rsi[-1] if rsi else None
        last_atr = atr_values[-1] if atr_values else None
        
        # Initialize signals and rationale
        signals = {
            "current_price": last_close,
            "sma50": last_sma50,
            "rsi14": last_rsi,
            "atr": last_atr,
        }
        
        rationale = []
        buy_score = 0.0
        sell_score = 0.0
        
        # --- TREND ANALYSIS ---
        trend = "FLAT"
        if last_sma50 is not None:
            if last_close > last_sma50 * 1.02:  # 2% above
                trend = "UP"
                buy_score += 0.2
                rationale.append(f"Price ${last_close:.2f} is 2%+ above SMA50 ${last_sma50:.2f}")
            elif last_close < last_sma50 * 0.98:  # 2% below
                trend = "DOWN"
                sell_score += 0.3
                rationale.append(f"Price ${last_close:.2f} is 2%+ below SMA50 ${last_sma50:.2f}")
            else:
                trend = "FLAT"
                rationale.append(f"Price ${last_close:.2f} is near SMA50 ${last_sma50:.2f}")
        
        # --- MOMENTUM ANALYSIS (RSI) ---
        if last_rsi is not None:
            if self.rsi_buy_low <= last_rsi <= self.rsi_buy_high:
                buy_score += 0.2
                rationale.append(f"RSI {last_rsi:.1f} in buy zone {self.rsi_buy_low}-{self.rsi_buy_high}")
            elif last_rsi > self.rsi_sell_high:
                sell_score += 0.2
                rationale.append(f"RSI {last_rsi:.1f} overbought (>{self.rsi_sell_high})")
            elif last_rsi < 30:
                buy_score += 0.1
                rationale.append(f"RSI {last_rsi:.1f} oversold (<30)")
        
        # --- DECISION LOGIC ---
        if existing_position and existing_position > 0:
            # Already have position - decide to hold or sell
            if sell_score > buy_score and sell_score > 0.3:
                decision = "SELL"
                confidence = min(sell_score, 1.0)
                rationale.insert(0, "Sell signals active on existing position")
            else:
                decision = "HOLD"
                confidence = 0.5
                rationale.insert(0, "Holding existing position")
        else:
            # No position - decide to buy or hold
            if buy_score > 0.3 and trend == "UP":
                decision = "BUY"
                confidence = min(buy_score, 1.0)
                rationale.insert(0, "Buy signals aligned: trend up + momentum favorable")
            else:
                decision = "HOLD"
                confidence = 0.3
                rationale.insert(0, "Insufficient buy signals")
        
        # --- POSITION SIZING ---
        position = {}
        risk = {}
        
        if decision == "BUY":
            # Calculate position size
            atr_for_sizing = last_atr if last_atr else (last_close * 0.05)
            size_result = RiskTools.calc_position_size(
                symbol=symbol,
                current_price=last_close,
                atr=atr_for_sizing,
                portfolio_equity=portfolio_equity,
                risk_budget_pct=0.01,
                multiplier=2.0
            )
            
            position = {
                "action_qty": int(size_result["shares"]),
                "action_value": size_result["cost"],
                "currency": "USD",
            }
            
            risk = {
                "risk_level": "medium" if confidence > 0.6 else "low",
                "max_loss_estimate": round(size_result["risk_amount"], 2),
                "stop_loss": size_result["stop_loss"],
                "take_profit": round(last_close * 1.05, 2),  # 5% above
            }
        
        elif decision == "SELL":
            # Sell existing percent of position
            sell_qty = int(existing_position * 0.5) if existing_position else 0
            
            position = {
                "action_qty": sell_qty,
                "action_value": sell_qty * last_close,
                "currency": "USD",
            }
            
            risk = {
                "risk_level": "low",
                "max_loss_estimate": 0,
                "stop_loss": None,
                "take_profit": None,
            }
        
        return self._create_decision(
            symbol=symbol,
            action=decision,
            confidence=confidence,
            signals={
                "trend": trend,
                "current_price": round(last_close, 2),
                "sma50": round(last_sma50, 2) if last_sma50 else None,
                "rsi14": round(last_rsi, 2) if last_rsi else None,
                "atr": round(last_atr, 2) if last_atr else None,
            },
            rationale=rationale,
            position=position,
            risk=risk,
        )
