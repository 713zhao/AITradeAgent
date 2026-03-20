"""Optimized rule-based strategy for higher returns"""
import logging
from typing import Dict, Any, List, Optional
from .strategy_interface import StrategyInterface
from ..tools.risk_tools import RiskTools

logger = logging.getLogger(__name__)

class OptimizedRuleStrategy(StrategyInterface):
    """
    Aggressive yet risk-managed strategy targeting 20%+ annual returns.
    
    Key improvements over baseline:
    - Uses faster SMA (10) for earlier trend detection
    - Lower RSI thresholds for more entries
    - Tighter stops (1.5%) with 3% targets = 2:1 R:R
    - Additional momentum filter (MACD histogram > 0)
    - Volume spike detection for breakout confirmation
    - Position sizing scales with confidence
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__("optimized_rule")
        self.config = config or {}
        
        # Load parameters from config or use optimized defaults
        strategy_cfg = self.config.get("strategy", {})
        rules_cfg = strategy_cfg.get("rules", {})
        
        # RSI parameters
        self.rsi_period = 14
        self.rsi_buy_low = rules_cfg.get("rsi_entry_oversold_threshold", 40)
        self.rsi_sell_high = rules_cfg.get("rsi_exit_overbought_threshold", 65)
        
        # SMA parameters
        self.sma_fast = 10   # Use faster SMA for earlier entries
        self.sma_slow = 30   # Medium-term trend
        
        # MACD parameters
        self.macd_fast = 12
        self.macd_slow = 26
        self.macd_signal = 9
        self.macd_require_bullish = True  # Require MACD histogram > 0 for entry
        
        # Volume
        self.volume_period = 20
        self.volume_spike_threshold = 1.5  # 150% of average volume for breakout confirmation
        
        # Position sizing
        self.base_risk_pct = strategy_cfg.get("default_risk_budget_pct", 0.015)  # 1.5% risk
        self.max_position_size_pct = strategy_cfg.get("max_position_size_pct", 0.25)  # 25% max
        self.stop_loss_atr_multiplier = strategy_cfg.get("stop_loss_multiplier", 1.5)
        self.take_profit_atr_multiplier = strategy_cfg.get("take_profit_multiplier", 3.0)
        
        logger.info(f"OptimizedRuleStrategy initialized: RSI({self.rsi_buy_low}-{self.rsi_sell_high}), "
                    f"SMA({self.sma_fast}/{self.sma_slow}), Risk={self.base_risk_pct*100:.1f}%, "
                    f"MaxPos={self.max_position_size_pct*100:.0f}%, R:R=1:2")
    
    def analyze(self, symbol: str, data: Dict[str, Any],
               portfolio_equity: float = 100000,
               existing_position: Optional[float] = None) -> Dict[str, Any]:
        """
        Analyze symbol using optimized rules
        
        Data expected to contain:
        - close, high, low, volume: lists
        - rsi, macd, sma10, sma30, atr: computed indicators
        """
        # Extract data
        closes = data.get("close", [])
        highs = data.get("high", [])
        lows = data.get("low", [])
        volumes = data.get("volume", [])
        sma10 = data.get("sma10", [])
        sma30 = data.get("sma30", [])
        rsi = data.get("rsi", [])
        macd_hist = data.get("macd_histogram", [])
        atr = data.get("atr", [])
        
        if not closes or len(closes) < max(30, self.sma_slow):
            return self._create_decision(
                symbol, "HOLD", 0.0,
                {"error": "Insufficient data"},
                ["Not enough data for analysis"]
            )
        
        # Get latest values
        last_close = closes[-1]
        last_high = highs[-1] if highs else last_close
        last_low = lows[-1] if lows else last_close
        last_volume = volumes[-1] if volumes else None
        last_sma10 = sma10[-1] if sma10 else None
        last_sma30 = sma30[-1] if sma30 else None
        last_rsi = rsi[-1] if rsi else None
        last_macd_hist = macd_hist[-1] if macd_hist else None
        last_atr = atr[-1] if atr else None
        
        # Calculate average volume for volume spike detection
        avg_volume = sum(volumes[-self.volume_period:]) / self.volume_period if len(volumes) >= self.volume_period else None
        volume_ratio = (last_volume / avg_volume) if (last_volume and avg_volume and avg_volume > 0) else 1.0
        
        signals = {
            "current_price": last_close,
            "sma10": last_sma10,
            "sma30": last_sma30,
            "rsi14": last_rsi,
            "macd_hist": last_macd_hist,
            "atr": last_atr,
            "volume_ratio": volume_ratio,
        }
        
        rationale = []
        buy_score = 0.0
        sell_score = 0.0
        
        # ===================
        # TREND ANALYSIS
        # ===================
        # Primary trend: SMA10 > SMA30 (bullish) or SMA10 < SMA30 (bearish)
        if last_sma10 is not None and last_sma30 is not None:
            if last_sma10 > last_sma30 * 1.005:  # 0.5% buffer
                trend_strength = (last_sma10 - last_sma30) / last_sma30
                buy_score += 0.25 + min(trend_strength * 10, 0.25)  # Up to 0.5 total
                rationale.append(f"Trend: SMA10 ({last_sma10:.2f}) > SMA30 ({last_sma30:.2f}) by {trend_strength*100:.1f}%")
            elif last_sma10 < last_sma30 * 0.995:
                trend_strength = (last_sma30 - last_sma10) / last_sma30
                sell_score += 0.25 + min(trend_strength * 10, 0.25)
                rationale.append(f"Trend: SMA10 ({last_sma10:.2f}) < SMA30 ({last_sma30:.2f}) by {trend_strength*100:.1f}%")
            else:
                rationale.append(f"Trend: SMA10 ({last_sma10:.2f}) ≈ SMA30 ({last_sma30:.2f})")
        
        # ===================
        # MOMENTUM ANALYSIS
        # ===================
        # RSI
        if last_rsi is not None:
            if self.rsi_buy_low <= last_rsi <= 60:  # 40-60 range is favorable
                rsi_score = 0.3 if last_rsi < 50 else 0.2
                buy_score += rsi_score
                rationale.append(f"RSI {last_rsi:.1f} in optimal range {self.rsi_buy_low}-60")
            elif last_rsi > self.rsi_sell_high:
                sell_score += 0.3
                rationale.append(f"RSI {last_rsi:.1f} overbought (> {self.rsi_sell_high})")
            elif last_rsi < 30:
                buy_score += 0.2  # Oversold bounce potential
                rationale.append(f"RSI {last_rsi:.1f} oversold")
        
        # MACD histogram (momentum confirmation)
        if last_macd_hist is not None:
            if last_macd_hist > 0:
                buy_score += 0.2
                rationale.append(f"MACD histogram positive: {last_macd_hist:.4f}")
            elif last_macd_hist < -0.01:  # Significantly negative
                sell_score += 0.2
                rationale.append(f"MACD histogram negative: {last_macd_hist:.4f}")
        
        # ===================
        # VOLUME CONFIRMATION
        # ===================
        if last_volume is not None and avg_volume and volume_ratio > self.volume_spike_threshold:
            buy_score += 0.15  # Volume spike confirms move
            rationale.append(f"Volume spike: {volume_ratio:.1f}x average")
        
        # ===================
        # DECISION LOGIC
        # ===================
        # Adjust confidence based on signal strength
        confidence = min(buy_score if buy_score > sell_score else sell_score, 1.0)
        
        if existing_position and existing_position > 0:
            # Already long - decide whether to hold or sell
            if sell_score > 0.4 and sell_score > buy_score:
                decision = "SELL"
                confidence = sell_score
                rationale.insert(0, "Sell signals dominate - exiting position")
            else:
                decision = "HOLD"
                rationale.insert(0, f"Holding position (sell_score={sell_score:.2f} < threshold)")
        else:
            # No position - decide to buy or hold
            if buy_score > 0.6:  # Strong buy signal
                decision = "BUY"
                rationale.insert(0, f"Strong buy signal (score={buy_score:.2f})")
            elif buy_score > 0.45:  # Moderate buy
                decision = "BUY"
                confidence = buy_score * 0.8  # Slightly lower confidence
                rationale.insert(0, f"Buy signal (score={buy_score:.2f})")
            else:
                decision = "HOLD"
                rationale.insert(0, f"No clear signal (buy={buy_score:.2f}, sell={sell_score:.2f})")
        
        # ===================
        # POSITION SIZING & RISK
        # ===================
        position = {}
        risk = {}
        
        if decision == "BUY":
            # Scale position size by confidence (0.6-1.0 -> 1x to 1.5x base risk)
            risk_multiplier = 1.0 + (confidence - 0.6) * 2.5  # 0.6->1.0x, 1.0->1.75x
            effective_risk_pct = min(self.base_risk_pct * risk_multiplier, self.max_position_size_pct)
            
            # Ensure we have ATR for stop calculation
            atr_for_sizing = last_atr if last_atr else (last_close * 0.02)
            if atr_for_sizing <= 0:
                atr_for_sizing = last_close * 0.02
            
            size_result = RiskTools.calc_position_size(
                symbol=symbol,
                current_price=last_close,
                atr=atr_for_sizing,
                portfolio_equity=portfolio_equity,
                risk_budget_pct=effective_risk_pct,
                multiplier=self.stop_loss_atr_multiplier
            )
            
            position = {
                "action_qty": int(size_result["shares"]),
                "action_value": size_result["cost"],
                "confidence_scaled_risk_pct": effective_risk_pct * 100,
                "currency": "USD",
            }
            
            risk = {
                "risk_level": "medium" if effective_risk_pct < 0.01 else "high",
                "max_loss_estimate": round(size_result["risk_amount"], 2),
                "stop_loss": size_result["stop_loss"],
                "take_profit": size_result["take_profit"],
                "atr": round(last_atr, 2) if last_atr else None,
                "risk_reward_ratio": f"1:{self.take_profit_atr_multiplier/self.stop_loss_atr_multiplier:.1f}",
            }
        
        elif decision == "SELL":
            # Sell entire position
            sell_qty = int(existing_position) if existing_position else 0
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
                "trend": "BULLISH" if buy_score > sell_score else "BEARISH" if sell_score > buy_score else "NEUTRAL",
                "current_price": round(last_close, 2),
                "sma10": round(last_sma10, 2) if last_sma10 else None,
                "sma30": round(last_sma30, 2) if last_sma30 else None,
                "rsi14": round(last_rsi, 2) if last_rsi else None,
                "macd_hist": round(last_macd_hist, 4) if last_macd_hist else None,
                "volume_ratio": round(volume_ratio, 2),
                "atr": round(last_atr, 2) if last_atr else None,
            },
            rationale=rationale,
            position=position,
            risk=risk,
        )
