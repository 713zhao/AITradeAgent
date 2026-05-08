"""
LLM-powered enhancements for Telegram trading notifications.

Provides:
- Anomaly detection and explanation
- Trade-level strategy suggestions
- Market regime enrichment
"""

import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class AnomalyDetection:
    """Container for detected anomalies"""
    has_anomaly: bool
    anomaly_type: Optional[str]
    explanation: str


def detect_trade_anomalies(
    indicators_snapshot: Any,
    target_price: Optional[float] = None,
    current_price: Optional[float] = None,
) -> AnomalyDetection:
    """
    Detect anomalies in trade setup (extreme RSI, volume spike, etc).
    
    Args:
        indicators_snapshot: The indicator snapshot with .indicators dict
        target_price: Target entry price
        current_price: Current market price
        
    Returns:
        AnomalyDetection with detected anomaly info
    """
    if indicators_snapshot is None:
        return AnomalyDetection(has_anomaly=False, anomaly_type=None, explanation="")

    try:
        ind = getattr(indicators_snapshot, "indicators", {})

        def _get_value(key: str) -> Optional[float]:
            r = ind.get(key)
            return r.value if r else None

        # Check RSI extremes
        rsi = _get_value("rsi")
        if rsi is not None:
            if rsi > 85:
                return AnomalyDetection(
                    has_anomaly=True,
                    anomaly_type="extreme_rsi",
                    explanation="⚠️ RSI Extreme: RSI > 85 (overbought condition)",
                )
            elif rsi < 15:
                return AnomalyDetection(
                    has_anomaly=True,
                    anomaly_type="extreme_rsi",
                    explanation="⚠️ RSI Extreme: RSI < 15 (oversold condition)",
                )

        # Check for unusual volume
        volume_sma = _get_value("volume_sma")
        volume = _get_value("volume")
        if volume_sma is not None and volume is not None and volume_sma > 0:
            volume_ratio = volume / volume_sma
            if volume_ratio > 2.5:
                return AnomalyDetection(
                    has_anomaly=True,
                    anomaly_type="volume_spike",
                    explanation=f"⚠️ Volume Surge: {volume_ratio:.1f}x average volume",
                )

        # Check for MACD divergence
        macd_line = _get_value("macd_line")
        macd_signal = _get_value("macd_signal")
        close_price = current_price or _get_value("close")
        
        if all(v is not None for v in [macd_line, macd_signal, close_price]):
            # Simple divergence: price down but MACD up, or vice versa
            macd_positive = macd_line > macd_signal
            price_up_from_signal = close_price > target_price if target_price else True
            if macd_positive != price_up_from_signal:
                return AnomalyDetection(
                    has_anomaly=True,
                    anomaly_type="macd_divergence",
                    explanation="⚠️ MACD Divergence: Price and MACD signals diverging",
                )

        # No anomalies found
        return AnomalyDetection(has_anomaly=False, anomaly_type=None, explanation="")

    except Exception as e:
        logger.warning(f"Anomaly detection failed: {e}")
        return AnomalyDetection(has_anomaly=False, anomaly_type=None, explanation="")


async def generate_trade_suggestion(
    llm_manager: Any,
    symbol: str,
    action: str,
    confidence: float,
    market_regime: Optional[Dict[str, Any]] = None,
    indicators_snapshot: Any = None,
    rationale: Optional[List[str]] = None,
) -> Optional[str]:
    """
    Generate a contextual trade suggestion using LLM.
    
    Args:
        llm_manager: LLMManager instance with .generate() method
        symbol: Stock symbol
        action: BUY or SELL
        confidence: Confidence level 0-1
        market_regime: Market regime dict with keys like 'risk_on', 'volatility_regime'
        indicators_snapshot: Technical indicator snapshot
        rationale: List of reason strings
        
    Returns:
        LLM-generated suggestion string, or None if generation fails
    """
    if llm_manager is None:
        return None

    try:
        ind_desc = ""
        if indicators_snapshot is not None:
            ind = getattr(indicators_snapshot, "indicators", {})

            def _get_value(key):
                r = ind.get(key)
                return r.value if r else None

            rsi = _get_value("rsi")
            macd_line = _get_value("macd_line")
            macd_signal = _get_value("macd_signal")
            bb_upper = _get_value("bb_upper")
            bb_lower = _get_value("bb_lower")
            close = _get_value("close")

            ind_parts = []
            if rsi is not None:
                ind_parts.append(f"RSI: {rsi:.1f}")
            if macd_line is not None and macd_signal is not None:
                ind_parts.append(f"MACD: {macd_line-macd_signal:+.4f}")
            if bb_upper is not None and bb_lower is not None and close is not None:
                bb_pos = (close - bb_lower) / (bb_upper - bb_lower) if bb_upper > bb_lower else 0.5
                ind_parts.append(f"BB Position: {bb_pos:.0%}")
            ind_desc = " | ".join(ind_parts)

        regime_desc = ""
        if market_regime:
            risk_on = market_regime.get("risk_on", False)
            vol_regime = market_regime.get("volatility_regime", "normal")
            regime_desc = f"Market: {'risk-on' if risk_on else 'risk-off'}, Volatility: {vol_regime}"

        rationale_desc = " ".join(rationale) if rationale else "No specific rationale provided"

        system_prompt = (
            "You are a concise trading advisor. Generate 1-2 sentence trade suggestions "
            "that are actionable, specific, and consider market conditions. Be direct."
        )

        user_prompt = f"""
Trade Setup:
- Symbol: {symbol}, Action: {action}, Confidence: {confidence*100:.0f}%
- Technical: {ind_desc or 'No indicators'}
- Market: {regime_desc or 'Normal regime'}
- Thesis: {rationale_desc}

Suggest ONE specific action or consideration for this trade in 1-2 sentences.
"""

        response = llm_manager.generate(
            prompt=user_prompt.strip(),
            system_prompt=system_prompt,
            temperature=0.3,
            use_cache=False,  # Trade-time suggestions should be fresh
        )

        if response and response.content:
            suggestion = response.content.strip()
            # Limit to reasonable length
            if len(suggestion) > 200:
                suggestion = suggestion[:197] + "..."
            return f"💡 Suggestion: {suggestion}"

        return None

    except Exception as e:
        logger.warning(f"Trade suggestion generation failed: {e}")
        return None


def format_market_regime_display(market_regime: Optional[Dict[str, Any]]) -> Optional[str]:
    """
    Format market regime as a display string for Telegram.
    
    Args:
        market_regime: Market regime dict
        
    Returns:
        Formatted string like "📍 Regime: Risk-On | Vol: High | VIX: 18.5"
    """
    if not market_regime:
        return None

    try:
        regime = market_regime.get("regime", {})
        risk_on = regime.get("risk_on", False)
        vol = regime.get("volatility_regime", "normal").lower()
        vix = regime.get("vix_current")

        parts = []
        
        # Risk regime indicator
        risk_icon = "🟢" if risk_on else "🔴"
        risk_label = "Risk-On" if risk_on else "Risk-Off"
        parts.append(f"{risk_icon} {risk_label}")

        # Volatility level
        if vol == "high":
            vol_icon = "📈"
        elif vol == "low":
            vol_icon = "📉"
        else:
            vol_icon = "➡️"
        parts.append(f"{vol_icon} Vol: {vol.capitalize()}")

        # VIX if available
        if vix is not None:
            parts.append(f"VIX: {vix:.1f}")

        return " | ".join(parts)

    except Exception as e:
        logger.warning(f"Market regime formatting failed: {e}")
        return None
