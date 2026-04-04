"""Regime Detection Agent - Optional LLM-powered market regime classifier.

Classifies current market conditions to enable strategy adaptation.
Disabled by default; enable via configuration.
"""
import logging
import os
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
import pandas as pd

from finance_service.agents.agent_interface import Agent, AgentReport
from finance_service.core.event_bus import Event, Events, get_event_bus
from finance_service.llm import LLMManager, LLMConfig
from finance_service.core.yaml_config import YAMLConfigEngine

logger = logging.getLogger(__name__)


@dataclass
class MarketRegime:
    """Market regime classification"""
    regime: str  # trending_bullish, trending_bearish, range_bound, high_volatility, low_volatility, mixed
    confidence: float  # 0.0-1.0
    description: str
    timestamp: datetime
    indicators_used: Optional[list] = None


class RegimeAgent(Agent):
    """Classifies market regime using technical data and optional LLM enhancement.

    If LLM is disabled or fails, falls back to deterministic rule-based classification.
    """

    @property
    def agent_id(self) -> str:
        return "regime_agent"

    @property
    def goal(self) -> str:
        return "Classify current market regime for strategy adaptation."

    def __init__(self, config_engine: YAMLConfigEngine):
        self.config_engine = config_engine
        self.event_bus = get_event_bus()
        self._llm_manager: Optional[LLMManager] = None
        self._current_regime: Optional[MarketRegime] = None
        self._init_llm()

    def _init_llm(self):
        """Initialize LLM if configured and enabled"""
        try:
            llm_enabled = self.config_engine.get("llm", "enabled", default=False)
            if not llm_enabled:
                logger.info("LLM disabled; RegimeAgent will use rule-based fallback")
                return

            module_enabled = self.config_engine.get("llm", "modules/market_regime/enabled", default=False)
            if not module_enabled:
                logger.info("Market regime LLM module disabled; using rule-based fallback")
                return

            # Build LLM config from YAML
            llm_config = LLMConfig(
                provider=self.config_engine.get("llm", "provider", default="openrouter"),
                api_key_env=self.config_engine.get("llm", "api_key_env", default="OPENROUTER_API_KEY"),
                base_url=self.config_engine.get("llm", "base_url", default=None),
                default_model=self.config_engine.get("llm", "modules/market_regime/model",
                                                   default=self.config_engine.get("llm", "model", default="openrouter/auto")),
                temperature=self.config_engine.get("llm", "modules/market_regime/temperature",
                                                  default=self.config_engine.get("llm", "temperature", default=0.2)),
                max_tokens=2000,
                timeout=self.config_engine.get("llm", "timeout", default=30),
                max_retries=self.config_engine.get("llm", "max_retries", default=3),
            )

            # Override from environment variables if present
            if os.getenv("LLM_PROVIDER"):
                llm_config.provider = os.getenv("LLM_PROVIDER")
            if os.getenv("GOOGLE_API_KEY"):
                llm_config.api_key_env = "GOOGLE_API_KEY"
            if os.getenv("TA_DEEP_THINK_MODEL"):
                llm_config.default_model = os.getenv("TA_DEEP_THINK_MODEL")

            self._llm_manager = LLMManager(llm_config)
            if self._llm_manager.validate():
                logger.info("RegimeAgent LLM initialized successfully")
            else:
                logger.warning("LLM validation failed; falling back to rule-based")
                self._llm_manager = None
        except Exception as e:
            logger.warning(f"Failed to initialize LLM for RegimeAgent: {e}; using fallback")

    async def run(self, payload: Dict[str, Any]) -> Optional[AgentReport]:
        """
        Classify market regime for a given symbol or for the overall market.

        Args:
            payload: Dict with keys:
                - symbol: Optional[str] - specific symbol to classify
                - ohlcv_data: Optional[pd.DataFrame] - OHLCV data (if not provided, will fetch)
                - indicators: Optional[Dict] - pre-computed indicators

        Returns:
            AgentReport with regime classification
        """
        symbol = payload.get("symbol")
        ohlcv_df = payload.get("ohlcv_data")
        indicators = payload.get("indicators")

        logger.info(f"RegimeAgent run for {symbol if symbol else 'market-wide'}")

        try:
            # Build indicator snapshot
            if ohlcv_df is None or indicators is None:
                # We need DataAgent to provide data; signal not ready yet
                logger.debug("Missing data; regime classification deferred")
                return None

            # Compute technical features
            features = self._extract_features(ohlcv_df, indicators)

            # Try LLM first if available
            regime = None
            if self._llm_manager:
                try:
                    regime = await self._classify_with_llm(symbol, features)
                except Exception as e:
                    logger.error(f"LLM classification failed: {e}; falling back to rules")

            # Fallback to deterministic rules
            if regime is None:
                regime = self._classify_with_rules(features)

            self._current_regime = regime

            # Publish event
            await self.event_bus.publish(Event(
                event_type=Events.MARKET_REGIME_UPDATED,
                data={"regime": asdict(regime), "symbol": symbol}
            ))

            return AgentReport(
                agent_id=self.agent_id,
                status="success",
                message=f"Regime classified as {regime.regime} (conf: {regime.confidence:.2%})",
                payload={"regime": asdict(regime)},
            )

        except Exception as e:
            logger.error(f"RegimeAgent error: {e}")
            return AgentReport(
                agent_id=self.agent_id,
                status="error",
                message=f"Regime classification failed: {e}",
                payload={},
            )

    def _extract_features(self, df: pd.DataFrame, indicators: Dict) -> Dict[str, Any]:
        """Extract features needed for regime classification"""
        # Get last row (current)
        latest = df.iloc[-1]

        # Price vs MAs
        close = latest['close'] if 'close' in latest else latest['Close']
        sma_50 = indicators.get('sma_50', close)
        sma_200 = indicators.get('sma_200', close)
        price_vs_sma50_pct = ((close - sma_50) / sma_50) * 100 if sma_50 else 0
        price_vs_sma200_pct = ((close - sma_200) / sma_200) * 100 if sma_200 else 0

        # MACD
        macd = indicators.get('macd', 0)
        macd_hist = indicators.get('macd_hist', 0)

        # RSI
        rsi = indicators.get('rsi', 50)

        # ATR volatility
        atr = indicators.get('atr', 0)
        atr_avg_90 = df['atr'].rolling(90).mean().iloc[-1] if 'atr' in df.columns and len(df) >= 90 else atr
        atr_ratio = atr / atr_avg_90 if atr_avg_90 and atr_avg_90 > 0 else 1.0

        # Trend: SMA50 vs SMA200
        trend_up = sma_50 > sma_200 if sma_50 and sma_200 else False
        trend_down = sma_50 < sma_200 if sma_50 and sma_200 else False

        # Volume spike?
        volume = latest.get('volume', 0)
        volume_avg = df['volume'].rolling(20).mean().iloc[-1] if 'volume' in df.columns else 0
        volume_ratio = volume / volume_avg if volume_avg and volume_avg > 0 else 1.0

        return {
            "close": close,
            "sma_50": sma_50,
            "sma_200": sma_200,
            "price_vs_sma50_pct": price_vs_sma50_pct,
            "price_vs_sma200_pct": price_vs_sma200_pct,
            "macd": macd,
            "macd_hist": macd_hist,
            "rsi": rsi,
            "atr": atr,
            "atr_ratio": atr_ratio,
            "trend_up": trend_up,
            "trend_down": trend_down,
            "volume_ratio": volume_ratio,
            "lookback_days": len(df),
        }

    async def _classify_with_llm(self, symbol: str, features: Dict[str, Any]) -> Optional[MarketRegime]:
        """Use LLM to classify regime"""
        prompt = self._build_regime_prompt(symbol, features)

        # Get prompt template from config if present
        template_path = self.config_engine.get("llm", "modules/market_regime/prompt_template", default=None)
        if template_path:
            prompt = self._load_prompt_template(template_path).format(**features)

        system_prompt = """You are a financial market regime classifier. Analyze the provided market data and classify the current regime.

Available regimes:
- trending_bullish: Price above major MAs, positive momentum, uptrend intact
- trending_bearish: Price below major MAs, negative momentum, downtrend intact
- range_bound: Sideways consolidation, low directional bias, mean-reversion favorable
- high_volatility: ATR significantly elevated (>2x normal), large price swings
- low_volatility: ATR suppressed (<0.5x normal), quiet consolidation
- mixed: Unclear, transitioning, or mixed signals

Output JSON only:
{
  "regime": "one of the above",
  "confidence": 0.0-1.0,
  "description": "one-sentence rationale"
}"""

        response = self._llm_manager.generate(prompt, system_prompt, temperature=0.2)

        try:
            # Extract JSON from response (LLM may wrap in ```json ... ```)
            content = response.content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            parsed = json.loads(content)
            return MarketRegime(
                regime=parsed["regime"],
                confidence=float(parsed["confidence"]),
                description=parsed["description"],
                timestamp=datetime.now(),
                indicators_used=list(features.keys()),
            )
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to parse LLM regime response: {e}; response: {response.content}")
            return None

    def _load_prompt_template(self, path: str) -> str:
        """Load prompt template from file"""
        full_path = os.path.join(self.config_engine.config_dir, path) if hasattr(self.config_engine, 'config_dir') else path
        with open(full_path, 'r') as f:
            return f.read()

    def _classify_with_rules(self, features: Dict[str, Any]) -> MarketRegime:
        """Deterministic rule-based classification fallback"""
        rsi = features.get('rsi', 50)
        macd = features.get('macd', 0)
        macd_hist = features.get('macd_hist', 0)
        atr_ratio = features.get('atr_ratio', 1.0)
        trend_up = features.get('trend_up', False)
        trend_down = features.get('trend_down', False)
        price_vs_sma200 = features.get('price_vs_sma200_pct', 0)

        # Volatility regimes first
        if atr_ratio > 2.0:
            regime = "high_volatility"
            confidence = min(atr_ratio / 3.0, 1.0)
            desc = f"ATR {atr_ratio:.1f}x normal → high volatility"
        elif atr_ratio < 0.5:
            regime = "low_volatility"
            confidence = min((0.5 - atr_ratio) / 0.5, 1.0)
            desc = f"ATR {atr_ratio:.1f}x normal → low volatility"
        # Trend regimes
        elif trend_up and price_vs_sma200 > 0:
            regime = "trending_bullish"
            confidence = 0.7 + min(abs(price_vs_sma200) / 10, 0.3)
            desc = f"Price {price_vs_sma200:.1f}% above SMA200, uptrend"
        elif trend_down and price_vs_sma200 < 0:
            regime = "trending_bearish"
            confidence = 0.7 + min(abs(price_vs_sma200) / 10, 0.3)
            desc = f"Price {abs(price_vs_sma200):.1f}% below SMA200, downtrend"
        else:
            regime = "range_bound"
            confidence = 0.6
            desc = "No clear trend; price oscillating near MAs"

        return MarketRegime(
            regime=regime,
            confidence=confidence,
            description=desc,
            timestamp=datetime.now(),
            indicators_used=list(features.keys()),
        )

    def get_current_regime(self) -> Optional[MarketRegime]:
        """Get the most recent regime classification"""
        return self._current_regime
