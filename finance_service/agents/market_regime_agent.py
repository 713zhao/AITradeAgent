"""MarketRegimeAgent - Broad market context provider.

Analyzes major indices (SP500, NASDAQ, DOW, VIX, RUSSELL2000) to assess:
- Index performance (1D, 5D, YTD)
- Technical posture (above/below key moving averages)
- Volatility regime (VIX level)
- Market breadth (advancers ratio, new highs/lows)
- Risk-on vs risk-off flag

This agent provides the 'market_context' for symbol selection and strategy adaptation.
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
import pandas as pd

from finance_service.agents.agent_interface import Agent, AgentReport
from finance_service.core.event_bus import get_event_bus
from finance_service.core.yaml_config import YAMLConfigEngine
from finance_service.agents.data_agent import DataAgent

logger = logging.getLogger(__name__)


@dataclass
class IndexMetrics:
    """Metrics for a single index"""
    symbol: str
    name: str
    price: float
    change_pct_1d: float
    change_pct_5d: float
    vs_sma20_pct: float
    vs_sma50_pct: float
    vs_sma200_pct: float
    ytd_return: float
    volume_ratio_vs_20d: float


@dataclass
class MarketBreadth:
    """Market breadth metrics"""
    advancers_ratio: float  # fraction of symbols advancing (0-1)
    new_highs_20d: int
    new_lows_20d: int
    volume_ratio_vs_avg: float
    symbols_above_sma20_pct: float
    symbols_above_sma50_pct: float


@dataclass
class MarketRegime:
    """Overall market regime assessment"""
    risk_on: bool
    momentum_favoring: bool
    volatility_regime: str  # "low", "normal", "high"
    trend_strength: str  # "weak", "moderate", "strong"
    summary: str
    indices: Dict[str, Dict[str, Any]]
    breadth: Dict[str, Any]


class MarketRegimeAgent(Agent):
    """Agent that computes broad market regime and breadth metrics."""

    @property
    def agent_id(self) -> str:
        return "market_regime_agent"

    @property
    def goal(self) -> str:
        return "Provide market-wide context for symbol selection and risk management."

    def __init__(self, config_engine: YAMLConfigEngine, data_agent: DataAgent, market_scanner=None):
        self.config_engine = config_engine
        self.data_agent = data_agent
        self.market_scanner = market_scanner
        self.event_bus = get_event_bus()
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_expiry: Optional[datetime] = None
        self.cache_ttl_minutes = self.config_engine.get(
            "market_regime_agent", "cache_ttl_minutes", default=60
        )

    async def run(self, payload: Optional[Dict[str, Any]] = None) -> Optional[AgentReport]:
        """
        Compute market regime metrics.

        Args:
            payload: Can include {'force_refresh': bool}

        Returns:
            AgentReport with payload containing:
            - regime: MarketRegime dataclass as dict
            - indices: dict of IndexMetrics per index
            - breadth: MarketBreadth as dict
            - timestamp: ISO string
        """
        # Check cache
        force = payload.get("force_refresh", False) if payload else False
        if not force and self._cache and self._cache_expiry and datetime.utcnow() < self._cache_expiry:
            return AgentReport(
                agent_id=self.agent_id,
                status="success",
                message="Market regime (cached)",
                payload=self._cache
            )

        try:
            # 1. Fetch index data
            indices_config = self.config_engine.get(
                "market_regime_agent", "indices",
                default={
                    "SP500":       {"symbol": "^GSPC",     "name": "S&P 500",               "market": "US"},
                    "NASDAQ":      {"symbol": "^IXIC",     "name": "NASDAQ Composite",      "market": "US"},
                    "DOW":         {"symbol": "^DJI",      "name": "Dow Jones Industrial",  "market": "US"},
                    "VIX":         {"symbol": "^VIX",      "name": "CBOE Volatility Index", "market": "US"},
                    "RUSSELL2000": {"symbol": "^RUT",      "name": "Russell 2000",          "market": "US"},
                    "HSI":         {"symbol": "^HSI",      "name": "Hang Seng Index",       "market": "HK"},
                    "HSCE":        {"symbol": "^HSCE",     "name": "H-Shares Index",        "market": "HK"},
                    "SHANGHAI":    {"symbol": "000001.SS", "name": "Shanghai Composite",    "market": "HK"},
                    "VHSI":        {"symbol": "^VHSI",     "name": "CBOE Hang Seng VIX",    "market": "HK"},
                }
            )

            index_metrics = {}
            for key, cfg in indices_config.items():
                symbol = cfg["symbol"]
                name = cfg["name"]
                try:
                    # Fetch 300 days of data to compute SMA200 (needs 200+ trading days)
                    end_dt = datetime.now().date()
                    start_dt = end_dt - timedelta(days=300)
                    df = await self.data_agent._fetch_data_for_symbol(
                        symbol, start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d"), "1d"
                    )
                    if df is None or len(df) < 20:
                        logger.warning(f"Insufficient data for index {symbol}")
                        continue

                    # Normalize column names to lowercase (DataAgent may return mixed case)
                    df.columns = [c.lower() for c in df.columns]

                    # Get latest close
                    latest = df.iloc[-1]
                    close = float(latest["close"])

                    # Compute changes
                    prev_close = float(df.iloc[-2]["close"]) if len(df) > 1 else close
                    change_1d = (close - prev_close) / prev_close * 100

                    # 5-day change
                    if len(df) >= 5:
                        close_5d = float(df.iloc[-5]["close"])
                        change_5d = (close - close_5d) / close_5d * 100
                    else:
                        change_5d = 0.0

                    # YTD return
                    first_close = float(df.iloc[0]["close"])
                    ytd = (close - first_close) / first_close * 100

                    # SMAs
                    sma20 = float(df["close"].rolling(20).mean().iloc[-1])
                    sma50 = float(df["close"].rolling(50).mean().iloc[-1])
                    sma200 = float(df["close"].rolling(200).mean().iloc[-1])

                    import math
                    vs_sma20_pct = (close - sma20) / sma20 * 100 if sma20 and not math.isnan(sma20) else 0.0
                    vs_sma50_pct = (close - sma50) / sma50 * 100 if sma50 and not math.isnan(sma50) else 0.0
                    vs_sma200_pct = (close - sma200) / sma200 * 100 if sma200 and not math.isnan(sma200) else 0.0

                    # Volume ratio (last day vs 20-day avg)
                    vol = float(latest["volume"])
                    vol_avg = float(df["volume"].rolling(20).mean().iloc[-1])
                    vol_ratio = vol / vol_avg if vol_avg > 0 else 1.0

                    index_metrics[key] = IndexMetrics(
                        symbol=symbol,
                        name=name,
                        price=close,
                        change_pct_1d=change_1d,
                        change_pct_5d=change_5d,
                        vs_sma20_pct=vs_sma20_pct,
                        vs_sma50_pct=vs_sma50_pct,
                        vs_sma200_pct=vs_sma200_pct,
                        ytd_return=ytd,
                        volume_ratio_vs_20d=vol_ratio
                    )
                except Exception as e:
                    logger.error(f"Failed to fetch/process index {symbol}: {e}")

            # 2. Compute market breadth if market_scanner available
            breadth = self._compute_breadth()

            # 3. Split indices by market and derive per-market regimes
            us_indices = {k: v for k, v in index_metrics.items()
                          if indices_config.get(k, {}).get("market", "US") == "US"}
            hk_indices = {k: v for k, v in index_metrics.items()
                          if indices_config.get(k, {}).get("market", "HK") == "HK"}

            regime_us = self._derive_regime(us_indices, breadth, market="US")
            regime_hk = self._derive_regime(hk_indices, None, market="HK")

            # Combined regime: risk-off if either market is risk-off
            combined_risk_on = regime_us.risk_on and regime_hk.risk_on
            combined_summary = f"US: {regime_us.summary} | HK: {regime_hk.summary}"
            from dataclasses import replace as dc_replace
            regime_combined = dc_replace(
                regime_us,
                risk_on=combined_risk_on,
                summary=combined_summary,
                indices={**regime_us.indices, **regime_hk.indices}
            )

            # Convert to dict for serialization
            indices_dict = {k: asdict(v) for k, v in index_metrics.items()}
            breadth_dict = asdict(breadth) if breadth else {}

            payload_out = {
                "indices": indices_dict,
                "breadth": breadth_dict,
                "regime": asdict(regime_combined),
                "regime_us": asdict(regime_us),
                "regime_hk": asdict(regime_hk),
                "timestamp": datetime.utcnow().isoformat()
            }

            # Cache result
            self._cache = payload_out
            self._cache_expiry = datetime.utcnow() + timedelta(minutes=self.cache_ttl_minutes)

            return AgentReport(
                agent_id=self.agent_id,
                status="success",
                message="Market regime computed",
                payload=payload_out
            )

        except Exception as e:
            logger.error(f"MarketRegimeAgent failed: {e}", exc_info=True)
            return AgentReport(
                agent_id=self.agent_id,
                status="error",
                message=str(e),
                payload={}
            )

    def _compute_breadth(self) -> Optional[MarketBreadth]:
        """Compute market breadth metrics from watchlist or index components."""
        if not self.market_scanner:
            logger.debug("No market_scanner provided; skipping breadth computation")
            return None

        try:
            watchlist_symbols = self.market_scanner.get_watchlist_symbols()
            if not watchlist_symbols:
                return None

            # We need latest prices vs SMAs. Lacking direct access, estimate from DataAgent cache
            # For simplicity, return placeholder metrics
            # In production, would fetch latest prices for all watchlist symbols and compute
            return MarketBreadth(
                advancers_ratio=0.60,  # Placeholder - would compute from price changes
                new_highs_20d=0,
                new_lows_20d=0,
                volume_ratio_vs_avg=1.0,
                symbols_above_sma20_pct=0.65,
                symbols_above_sma50_pct=0.58
            )
        except Exception as e:
            logger.warning(f"Breadth computation failed: {e}")
            return None

    def _derive_regime(self, index_metrics: Dict[str, IndexMetrics], breadth: Optional[MarketBreadth], market: str = "US") -> MarketRegime:
        """Derive overall market regime flags from index metrics."""
        # Defaults
        risk_on = True
        momentum_favoring = True
        volatility_regime = "normal"
        trend_strength = "moderate"
        summary_parts = []

        # Use primary indicators per market
        if market == "HK":
            sp500 = index_metrics.get("HSI")       # Hang Seng as primary trend indicator
            vix   = index_metrics.get("VHSI")      # HK volatility index
            nasdaq = index_metrics.get("HSCE")     # H-shares as momentum proxy
        else:
            sp500 = index_metrics.get("SP500")
            vix   = index_metrics.get("VIX")
            nasdaq = index_metrics.get("NASDAQ")

        market_label = "HSI" if market == "HK" else "SP500"

        if sp500:
            # Trend: above SMA200 is bullish trend
            if sp500.vs_sma200_pct > 2:
                trend_strength = "strong"
            elif sp500.vs_sma200_pct < -2:
                trend_strength = "weak"
                risk_on = False
                momentum_favoring = False
            else:
                trend_strength = "moderate"

            summary_parts.append(f"{market_label} vs SMA200: {sp500.vs_sma200_pct:.1f}%")

        if vix:
            if vix.price > 30:
                volatility_regime = "high"
                risk_on = False
                summary_parts.append(f"VIX elevated at {vix.price:.1f}")
            elif vix.price < 15:
                volatility_regime = "low"
                summary_parts.append(f"VIX low at {vix.price:.1f}")
            else:
                summary_parts.append(f"VIX normal at {vix.price:.1f}")

        if nasdaq:
            if nasdaq.change_pct_1d > 1.0:
                momentum_favoring = True
            elif nasdaq.change_pct_1d < -1.0:
                momentum_favoring = False
                risk_on = False

        # Breadth adjustments
        if breadth:
            if breadth.advancers_ratio < 0.45:
                risk_on = False
                momentum_favoring = False
                summary_parts.append(f"Breadth weak ({(breadth.advancers_ratio*100):.0f}% advancers)")
            elif breadth.advancers_ratio > 0.65:
                summary_parts.append(f"Breadth strong ({(breadth.advancers_ratio*100):.0f}% advancers)")

        # Build summary
        prefix = f"[{market}] "
        if risk_on:
            summary = prefix + "Risk-on: " + "; ".join(summary_parts)
        else:
            summary = prefix + "Risk-off: " + "; ".join(summary_parts)

        return MarketRegime(
            risk_on=risk_on,
            momentum_favoring=momentum_favoring,
            volatility_regime=volatility_regime,
            trend_strength=trend_strength,
            summary=summary,
            indices={k: asdict(v) for k, v in index_metrics.items()},
            breadth=asdict(breadth) if breadth else {}
        )
