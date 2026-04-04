"""SymbolSelectorAgent - LLM-powered stock ranking and selection.

Analyzes candidate symbols using technicals, fundamentals, news, market regime, and macro context
to produce a ranked watchlist with position sizing suggestions.

Integrates with the main pipeline after MarketScanner discovery.
"""
import logging
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
import asyncio
import os
import pandas as pd

from finance_service.agents.agent_interface import Agent, AgentReport
from finance_service.core.event_bus import get_event_bus
from finance_service.core.yaml_config import YAMLConfigEngine
from finance_service.agents.data_agent import DataAgent
from finance_service.agents.market_scanner_agent import MarketScannerAgent
from finance_service.agents.market_regime_agent import MarketRegimeAgent
from finance_service.agents.macro_news_agent import MacroNewsAgent
from finance_service.agents.analysis_agent import AnalysisAgent
from finance_service.agents.news_agent import NewsAgent


logger = logging.getLogger(__name__)


@dataclass
class CandidateData:
    """Structured data for a single candidate symbol"""
    symbol: str
    theme: str
    technical_indicators: Dict[str, Any]
    price_action: Dict[str, Any]
    fundamentals: Optional[Dict[str, Any]]
    news_sentiment: Dict[str, Any]
    liquidity_metrics: Dict[str, Any]
    risk_metrics: Dict[str, Any]


class SymbolSelectorAgent(Agent):
    """Agent that ranks watchlist symbols using LLM synthesis."""

    @property
    def agent_id(self) -> str:
        return "symbol_selector_agent"

    @property
    def goal(self) -> str:
        return "Rank and select high-conviction trade candidates using LLM evaluation."

    def __init__(self, config_engine: YAMLConfigEngine,
                 data_agent: DataAgent,
                 market_scanner: MarketScannerAgent,
                 market_regime_agent: MarketRegimeAgent,
                 macro_news_agent: MacroNewsAgent,
                 analysis_agent: AnalysisAgent,
                 news_agent: NewsAgent):
        self.config_engine = config_engine
        self.data_agent = data_agent
        self.market_scanner = market_scanner
        self.market_regime_agent = market_regime_agent
        self.macro_news_agent = macro_news_agent
        self.analysis_agent = analysis_agent
        self.news_agent = news_agent
        self.event_bus = get_event_bus()
        self._llm_manager = self._init_llm()
        self.cache_ttl_hours = self.config_engine.get("symbol_selector", "cache_ttl_hours", default=24)
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_key: Optional[str] = None
        self._cache_expiry: Optional[datetime] = None

    def _init_llm(self):
        """Initialize LLM client if enabled."""
        try:
            from finance_service.llm import LLMManager, LLMConfig
            llm_enabled = self.config_engine.get("llm", "enabled", default=False)
            if not llm_enabled:
                logger.info("LLM disabled; SymbolSelector will not be used")
                return None

            module_enabled = self.config_engine.get("symbol_selector", "enabled", default=False)
            if not module_enabled:
                logger.info("SymbolSelector disabled in config")
                return None

            llm_config = LLMConfig(
                provider=self.config_engine.get("llm", "provider", default="openrouter"),
                api_key_env=self.config_engine.get("llm", "api_key_env", default="OPENROUTER_API_KEY"),
                base_url=self.config_engine.get("llm", "base_url", default=None),
                default_model=self.config_engine.get("symbol_selector", "model",
                                                   default=self.config_engine.get("llm", "model", default="openrouter/auto")),
                temperature=self.config_engine.get("symbol_selector", "temperature", default=0.2),
                max_tokens=4000,
                timeout=self.config_engine.get("llm", "timeout", default=30),
                max_retries=self.config_engine.get("llm", "max_retries", default=3),
            )

            # Override from environment variables if present
            if os.getenv("LLM_PROVIDER"):
                llm_config.provider = os.getenv("LLM_PROVIDER")
            if os.getenv("GOOGLE_API_KEY"):
                # Use GOOGLE_API_KEY directly as the environment variable name for the API key
                llm_config.api_key_env = "GOOGLE_API_KEY"
            # Model selection: TA_QUICK_THINK_MODEL for SymbolSelector (fast), fallback to TA_DEEP_THINK_MODEL
            if os.getenv("TA_QUICK_THINK_MODEL"):
                llm_config.default_model = os.getenv("TA_QUICK_THINK_MODEL")
            elif os.getenv("TA_DEEP_THINK_MODEL"):
                llm_config.default_model = os.getenv("TA_DEEP_THINK_MODEL")

            manager = LLMManager(llm_config)
            if manager.validate():
                logger.info("SymbolSelectorAgent LLM initialized")
                return manager
            else:
                logger.warning("LLM validation failed; SymbolSelector disabled")
                return None
        except Exception as e:
            logger.warning(f"Failed to init LLM for SymbolSelector: {e}")
            return None

    async def run(self, payload: Dict[str, Any]) -> Optional[AgentReport]:
        """
        Rank candidate symbols using LLM synthesis.

        Args:
            payload: {
                "symbols": List[str]  (candidate symbols from discovery)
            }

        Returns:
            AgentReport with payload:
            {
                "rankings": [{symbol, total_score, breakdown, rationale, position_size_pct}],
                "rejected": [{symbol, reason}],
                "market_context": {regime, macro_news, macro_sentiment}
            }
        """
        if not self._llm_manager:
            logger.warning("SymbolSelectorAgent disabled; returning empty rankings")
            return AgentReport(
                agent_id=self.agent_id,
                status="skipped",
                message="LLM not available",
                payload={"rankings": [], "rejected": []}
            )

        candidate_symbols = payload.get("symbols", [])
        if not candidate_symbols:
            return AgentReport(
                agent_id=self.agent_id,
                status="error",
                message="No candidates provided",
                payload={"rankings": [], "rejected": []}
            )

        # Cache key based on symbols set + regime hash
        cache_key = self._make_cache_key(candidate_symbols)
        force = payload.get("force_refresh", False)
        if not force and self._cache and self._cache_key == cache_key and self._cache_expiry and datetime.utcnow() < self._cache_expiry:
            return AgentReport(
                agent_id=self.agent_id,
                status="success",
                message="Rankings (cached)",
                payload=self._cache
            )

        try:
            logger.info(f"SymbolSelector evaluating {len(candidate_symbols)} candidates")

            # 1. Gather market context (regime + macro)
            regime_report = await self.market_regime_agent.run()
            macro_report = await self.macro_news_agent.run()

            market_context = {
                "regime": regime_report.payload.get("regime", {}),
                "macro_sentiment_score": macro_report.payload.get("macro_sentiment_score", 0.0),
                "macro_catalysts": macro_report.payload.get("macro_catalysts", []),
                "risk_events": macro_report.payload.get("risk_events", [])
            }

            # 2. Gather candidate data in parallel
            candidate_data_list = await self._gather_candidate_data(candidate_symbols)

            # 3. Build prompt
            prompt = self._build_prompt(candidate_data_list, market_context)

            # 4. Call LLM
            # Use provider.generate_async to avoid asyncio.run() inside async context
            llm_response = await self._llm_manager.provider.generate_async(prompt)
            llm_text = llm_response.content if hasattr(llm_response, "content") else str(llm_response)
            rankings = self._parse_llm_response(llm_text)

            # 5. Cache and return
            result = {
                "rankings": rankings,
                "rejected": self._filter_rejected(candidate_data_list, rankings),
                "market_context": market_context,
                "generated_at": datetime.utcnow().isoformat()
            }

            self._cache = result
            self._cache_key = cache_key
            self._cache_expiry = datetime.utcnow() + timedelta(hours=self.cache_ttl_hours)

            return AgentReport(
                agent_id=self.agent_id,
                status="success",
                message=f"Ranked {len(rankings)} symbols via LLM",
                payload=result
            )

        except Exception as e:
            logger.error(f"SymbolSelector failed: {e}", exc_info=True)
            return AgentReport(
                agent_id=self.agent_id,
                status="error",
                message=str(e),
                payload={"rankings": [], "rejected": []}
            )

    def _make_cache_key(self, symbols: List[str]) -> str:
        """Create cache key from sorted symbols + market regime snapshot."""
        sorted_syms = sorted(symbols)
        # Include a hash of yesterday's regime to invalidate if regime changes
        # For simplicity, just use symbol list hash
        import hashlib
        return hashlib.md5("|".join(sorted_syms).encode()).hexdigest()[:8]

    async def _gather_candidate_data(self, symbols: List[str]) -> List[CandidateData]:
        """Gather all needed data for candidate symbols in parallel."""
        # Limit to top N to control cost
        max_symbols = self.config_engine.get("symbol_selector", "max_input_symbols", default=50)
        symbols = symbols[:max_symbols]

        tasks = []
        for sym in symbols:
            tasks.append(self._fetch_candidate_data(sym))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [r for r in results if not isinstance(r, Exception) and r is not None]

    async def _fetch_candidate_data(self, symbol: str) -> Optional[CandidateData]:
        """Fetch all required data for a single symbol."""
        try:
            # 1. Fetch OHLCV (30d)
            end_dt = datetime.now().date()
            start_dt = end_dt - timedelta(days=60)
            df = await self.data_agent._fetch_data_for_symbol(
                symbol, start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d"), "1d"
            )
            if df is None or len(df) < 20:
                logger.warning(f"Insufficient data for {symbol}")
                return None

            latest = df.iloc[-1]
            close = float(latest["close"])

            # 2. Compute technical indicators (using AnalysisAgent logic but inline for speed)
            # We'll compute a subset directly to avoid extra agent call
            sma20 = float(df["close"].rolling(20).mean().iloc[-1])
            sma50 = float(df["close"].rolling(50).mean().iloc[-1])
            sma200 = float(df["close"].rolling(200).mean().iloc[-1])
            rsi = self._compute_rsi(df["close"], 14)
            macd_line = float(df["close"].ewm(span=12).mean().iloc[-1] - df["close"].ewm(span=26).mean().iloc[-1])
            signal_line = float(df["close"].ewm(span=12).mean().ewm(span=9).mean().iloc[-1] - df["close"].ewm(span=26).mean().ewm(span=9).mean().iloc[-1])
            atr = self._compute_atr(df, 14)

            technical_indicators = {
                "rsi": round(rsi, 2),
                "macd": {"value": round(macd_line, 2), "histogram": round(macd_line - signal_line, 2)},
                "sma_20": round(sma20, 2),
                "sma_50": round(sma50, 2),
                "sma_200": round(sma200, 2),
                "atr": round(atr, 2),
                "bb_width": 0.0  # placeholder
            }

            # 3. Price action metrics
            price_vs_sma20_pct = (close - sma20) / sma20 * 100
            price_vs_sma200_pct = (close - sma200) / sma200 * 100
            high_52w = float(df["high"].iloc[-252:].max()) if len(df) >= 252 else close
            low_52w = float(df["low"].iloc[-252:].min()) if len(df) >= 252 else close
            ytd_return = (close - float(df.iloc[0]["close"])) / float(df.iloc[0]["close"]) * 100

            price_action = {
                "current_price": round(close, 2),
                "price_vs_sma20_pct": round(price_vs_sma20_pct, 2),
                "price_vs_sma200_pct": round(price_vs_sma200_pct, 2),
                "52w_high": round(high_52w, 2),
                "52w_low": round(low_52w, 2),
                "ytd_return_pct": round(ytd_return, 2)
            }

            # 4. Liquidity metrics (from DataAgent/DataCache or quick quote)
            # For now, use plausible estimates based on symbol type (will refine)
            avg_volume = float(df["volume"].rolling(20).mean().iloc[-1])
            avg_price = float(df["close"].rolling(20).mean().iloc[-1])
            avg_dollar_volume = avg_volume * avg_price
            liquidity_tier = "high" if avg_dollar_volume > 50_000_000 else "medium" if avg_dollar_volume > 10_000_000 else "low"

            liquidity_metrics = {
                "avg_daily_volume_20d": int(avg_volume),
                "avg_dollar_volume_20d": int(avg_dollar_volume),
                "liquidity_tier": liquidity_tier
            }

            # 5. Risk metrics (beta, correlation)
            # For now, placeholder (would compute vs SPY)
            risk_metrics = {
                "beta_estimate": 1.2 if liquidity_tier == "high" else 1.0,
                "days_to_earnings": -1  # unknown
            }

            # 6. Fundamentals (would come from FundamentalsAgent; placeholder)
            fundamentals = None

            # 7. News sentiment (from NewsAgent cache if available)
            # Quick try: if NewsAgent has cached data for this symbol, we could extract
            # For now, request via news_agent.run
            try:
                news_report = await self.news_agent.run(symbol)
                news_sentiment = {
                    "sentiment_score": news_report.payload.get("sentiment_score", 0.0),
                    "sentiment_label": news_report.payload.get("sentiment_label", "neutral"),
                    "catalysts": news_report.payload.get("catalysts", []),
                    "article_count": news_report.payload.get("news_count", 0)
                }
            except Exception as e:
                logger.debug(f"Failed to fetch news for {symbol}: {e}")
                news_sentiment = {"sentiment_score": 0.0, "sentiment_label": "neutral", "catalysts": [], "article_count": 0}

            # 8. Theme from market_scanner
            theme = "unknown"
            try:
                watchlist = self.market_scanner.get_watchlist()
                for item in watchlist:
                    if item.get("symbol") == symbol:
                        theme = item.get("theme", "unknown")
                        break
            except:
                pass

            return CandidateData(
                symbol=symbol,
                theme=theme,
                technical_indicators=technical_indicators,
                price_action=price_action,
                fundamentals=fundamentals,
                news_sentiment=news_sentiment,
                liquidity_metrics=liquidity_metrics,
                risk_metrics=risk_metrics
            )

        except Exception as e:
            logger.error(f"Failed to gather data for {symbol}: {e}")
            return None

    def _compute_rsi(self, prices: pd.Series, period: int = 14) -> float:
        """Simple RSI calculation."""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss if loss.iloc[-1] != 0 else 0
        rsi = 100 - (100 / (1 + rs.iloc[-1]))
        return rsi if not pd.isna(rsi) else 50.0

    def _compute_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """Compute Average True Range."""
        high = df["high"]
        low = df["low"]
        close = df["close"].shift()
        tr1 = high - low
        tr2 = (high - close).abs()
        tr3 = (low - close).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(period).mean().iloc[-1]
        return float(atr) if not pd.isna(atr) else 0.0

    def _build_prompt(self, candidates: List[CandidateData], market_context: Dict[str, Any]) -> str:
        """Construct the LLM prompt."""
        # Build market context section
        mc = market_context
        regime = mc.get("regime", {})
        indices = mc.get("indices", {})

        indices_text = ""
        for name, data in indices.items():
            indices_text += f"- {name}: {data.get('price', 0):.2f} ({data.get('change_pct_1d', 0):.1f}% today), vs SMA200: {data.get('vs_sma200_pct', 0):.1f}%, YTD: {data.get('ytd_return', 0):.1f}%\n"

        breadth = mc.get("breadth", {})
        breadth_text = f"Advancers ratio: {(breadth.get('advancers_ratio', 0)*100):.0f}%, " \
                       f"Symbols above SMA50: {(breadth.get('symbols_above_sma50_pct', 0)*100):.0f}%"

        macro_sent = mc.get("macro_sentiment_score", 0.0)
        macro_cats = "; ".join(mc.get("macro_catalysts", [])[:5])
        risk_events = "; ".join(mc.get("risk_events", [])[:5])

        # Build candidates JSON
        candidates_json = []
        for c in candidates:
            cand_dict = {
                "symbol": c.symbol,
                "theme": c.theme,
                "technical": {
                    "rsi": c.technical_indicators.get("rsi"),
                    "macd": c.technical_indicators.get("macd", {}).get("value"),
                    "sma20_vs_price_pct": c.price_action.get("price_vs_sma20_pct"),
                    "sma50_vs_price_pct": c.price_action.get("price_vs_sma200_pct"),
                    "atr": c.technical_indicators.get("atr")
                },
                "price": c.price_action.get("current_price"),
                "performance": {
                    "ytd_return_pct": c.price_action.get("ytd_return_pct"),
                    "52w_high": c.price_action.get("52w_high"),
                    "52w_low": c.price_action.get("52w_low")
                },
                "news": {
                    "sentiment_score": c.news_sentiment.get("sentiment_score"),
                    "catalysts": c.news_sentiment.get("catalysts", [])[:3]
                },
                "liquidity": {
                    "avg_dollar_volume_20d": "${:,.0f}".format(c.liquidity_metrics.get("avg_dollar_volume_20d") or 0),
                    "tier": c.liquidity_metrics.get("liquidity_tier")
                },
                "risk": {
                    "beta_estimate": c.risk_metrics.get("beta_estimate"),
                    "days_to_earnings": c.risk_metrics.get("days_to_earnings")
                }
            }
            candidates_json.append(cand_dict)

        prompt = f"""You are an expert equity analyst and portfolio manager. Your task is to rank a list of candidate stocks for a multi-strategy trading system.

## System Context
- Current market regime: {regime.get('summary', 'Unknown')}
- Risk-on flag: {regime.get('risk_on', '?')}
- Volatility regime: {regime.get('volatility_regime', '?')}
- Trend strength: {regime.get('trend_strength', '?')}
- Portfolio objective: Capture medium-term momentum (2-4 weeks) with risk management
- Max concurrent positions: 5, max position size 2% each

## Market Overview

### Major Indices
{indices_text}
Market breadth: {breadth_text}

### Macro Environment
- Macro sentiment score: {macro_sent:.2f} (-1 to +1)
- Recent catalysts: {macro_cats}
- Upcoming risk events: {risk_events}

## Candidates
Each candidate includes technicals, price action, news, liquidity, and risk metrics.

{json.dumps(candidates_json, indent=2)}

## Evaluation Framework

Score each candidate 0-10 on:

1. **Technical Conviction**: RSI range (30-70 ideal), MACD positive/histogram increasing, price above SMA20 & SMA50, ATR reasonable
2. **Catalyst Alignment**: Recent news catalysts, upcoming events (earnings, product launches), narrative strength
3. **Fundamental Quality** (if available): Earnings growth, revenue growth, reasonable valuation
4. **Risk-Adjusted Appeal**: Liquidity (ensure dollar volume > $20M), avoid high beta (>1.8), watch earnings date proximity
5. **Regime Fit**: Does this stock thrive in current market regime? (e.g., tech in risk-on, defensives in risk-off)

Apply context:
- If risk-on: favor high-beta momentum, growth, tech, ignore moderate valuations
- If risk-off: favor low-beta, quality, dividends, strong balance sheets
- High volatility: reduce conviction scores, widen suggested stops
- Near earnings: dock 2 points unless strong conviction and willing to hold through event

## Output (strict JSON)
```json
{{
  "rankings": [
    {{
      "symbol": "NVDA",
      "total_score": 85,
      "breakdown": {{"technical": 9, "catalyst": 8, "fundamental": 9, "risk_adjusted": 8, "regime_fit": 9}},
      "rationale": "Strong technical uptrend with bullish MACD, positive AI news flow, solid earnings growth, and perfect regime fit. Minor caution: earnings in 2 weeks.",
      "position_size_pct": 2.0,
      "suggested_stop_pct": 8.0
    }},
    ...
  ],
  "summary": "Top 5 candidates show strong momentum aligned with AI theme. Market regime bullish but cautious due to upcoming Fed meeting."
}}
```

IMPORTANT:
- Return ONLY valid JSON, no extra text
- Include at least the top 5 symbols (more is fine)
- total_score must be 0-100 (sum of 0-10 scores * 2)
- position_size_pct between 0.5 and 2.0
- suggested_stop_pct between 5 and 15
"""
        return prompt

    def _parse_llm_response(self, response: str) -> List[Dict[str, Any]]:
        """Parse LLM JSON response into ranking list."""
        try:
            # Extract JSON if wrapped in ```json blocks
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                json_str = response.split("```")[1].strip()
            else:
                json_str = response.strip()

            data = json.loads(json_str)
            rankings = data.get("rankings", [])

            # Validate and sanitize
            for r in rankings:
                if "total_score" not in r:
                    r["total_score"] = sum(r.get("breakdown", {}).values()) * 2
                if "position_size_pct" not in r:
                    r["position_size_pct"] = 1.0
                if "suggested_stop_pct" not in r:
                    r["suggested_stop_pct"] = 8.0
                # Clamp values
                r["position_size_pct"] = max(0.5, min(2.0, float(r["position_size_pct"])))
                r["suggested_stop_pct"] = max(5.0, min(15.0, float(r["suggested_stop_pct"])))

            return rankings
        except Exception as e:
            logger.error(f"Failed to parse LLM response: {e}\nResponse: {response[:200]}")
            return []

    def _filter_rejected(self, candidates: List[CandidateData], rankings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Identify symbols that were not ranked (likely filtered out by LLM)."""
        ranked_symbols = {r["symbol"] for r in rankings}
        rejected = []
        for c in candidates:
            if c.symbol not in ranked_symbols:
                rejected.append({
                    "symbol": c.symbol,
                    "reason": "Not included in LLM ranking (low conviction)"
                })
        return rejected
