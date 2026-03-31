"""Market Scanner - 3-Tier scanning: Discovery (daily), Price Monitor (15min), Exit Monitor (5min)"""
import json
import logging
import asyncio
import os
from dataclasses import asdict
from datetime import datetime
from typing import List, Dict, Optional, Set, Tuple, Any
from finance_service.core.yaml_config import YAMLConfigEngine
from finance_service.agents.agent_interface import Agent, AgentReport
from finance_service.core.events import Event, Events, get_event_bus

logger = logging.getLogger(__name__)


class MarketScannerAgent(Agent):
    """
    Market Scanner Agent — 3-tier scanning architecture:
    
    Tier 1 (Discovery): Daily full scan of wide universe → rank → top N per theme with rating.
    Tier 2 (Price Monitor): Every 15 min fetch latest price for watchlist symbols.
    Tier 3 (Exit Monitor): Handled by ExitAgent (every 5 min, held positions only).
    """

    @property
    def agent_id(self) -> str:
        return "market_scanner_agent"

    @property
    def goal(self) -> str:
        return "Discover promising stocks via daily ranking and monitor watchlist prices every 15 minutes."

    def __init__(self, config_engine: YAMLConfigEngine):
        self.config = config_engine
        self._whitelist_enabled = self.config.get("finance", "universe/whitelist/enabled", default=False)
        self._whitelist_symbols = set(self.config.get("finance", "universe/whitelist/symbols", default=[]))
        self.event_bus = get_event_bus()
        self._score_cache: Dict[str, float] = {}
        # Watchlist: populated by discovery scan, consumed by price monitor
        self._watchlist: List[Dict[str, Any]] = []  # [{symbol, theme, rating, rank}, ...]
        self._watchlist_symbols: List[str] = []      # flat list for quick access
        self._last_discovery: Optional[str] = None    # ISO timestamp of last discovery
        # Persist watchlist so it survives restarts
        self._watchlist_path = os.path.join(
            os.path.dirname(__file__), "..", "storage", "watchlist.json"
        )
        self._load_watchlist()
        logger.info(f"MarketScannerAgent initialized (whitelist_enabled={self._whitelist_enabled})")

    # ─── Public accessors ───────────────────────────────────────────

    def get_all_symbols(self) -> List[str]:
        """Get all configured symbols from universe."""
        symbols = self.config.get("finance", "universe/all_symbols", default=[])
        return list(set(symbols))

    def get_symbols_by_theme(self, theme: str) -> List[str]:
        """Get symbols for a specific theme."""
        themes = self.config.get("finance", "universe/themes", default=[])
        for t in themes:
            if isinstance(t, dict) and t.get("name", "").lower() == theme.lower():
                return list(set(t.get("symbols", [])))
        logger.warning(f"Theme '{theme}' not found")
        return []

    def get_available_themes(self) -> List[str]:
        """Get all available theme names."""
        themes = self.config.get("finance", "universe/themes", default=[])
        return [t.get("name", "") for t in themes if isinstance(t, dict)]

    def get_watchlist(self) -> List[Dict[str, Any]]:
        """Return current watchlist (populated by last discovery scan)."""
        return list(self._watchlist)

    def get_watchlist_symbols(self) -> List[str]:
        """Return flat symbol list from watchlist."""
        return list(self._watchlist_symbols)

    def _load_watchlist(self) -> None:
        """Load persisted watchlist from disk (called on init)."""
        try:
            path = os.path.abspath(self._watchlist_path)
            if os.path.exists(path):
                with open(path, "r") as f:
                    data = json.load(f)
                self._watchlist = data.get("watchlist", [])
                self._watchlist_symbols = [r["symbol"] for r in self._watchlist]
                self._last_discovery = data.get("last_discovery")
                logger.info(
                    f"Loaded persisted watchlist: {len(self._watchlist)} symbols "
                    f"(last discovery: {self._last_discovery})"
                )
        except Exception as e:
            logger.warning(f"Could not load persisted watchlist: {e}")

    def _save_watchlist(self) -> None:
        """Persist current watchlist to disk after each discovery scan."""
        try:
            path = os.path.abspath(self._watchlist_path)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                json.dump(
                    {
                        "last_discovery": self._last_discovery,
                        "watchlist": self._watchlist,
                    },
                    f,
                    indent=2,
                )
            logger.info(f"Watchlist persisted: {len(self._watchlist)} symbols → {path}")
        except Exception as e:
            logger.warning(f"Could not persist watchlist: {e}")

    # ─── Tier 1: Discovery Scan (daily) ─────────────────────────────

    async def run(self, include_themes: Optional[List[str]] = None,
                  min_liquidity: float = 0.0,
                  limit: int = 10,
                  data_agent=None) -> Optional[AgentReport]:
        """
        Tier 1 — Full discovery scan.
        
        Scans the entire universe, ranks by composite score,
        selects top N per theme, and builds the watchlist.
        
        Args:
            include_themes: Themes to scan (None = all)
            min_liquidity: Minimum average daily volume threshold
            limit: Max symbols per theme (default 10)
            data_agent: DataAgent for fetching volume/price data
        
        Returns:
            AgentReport with ranked symbols and ratings
        """
        top_n = self.config.get("finance", "scanner/discovery_top_n_per_theme", default=limit)
        logger.info(f"[Discovery] Running full scan: themes={include_themes}, top_n={top_n}, min_liq={min_liquidity}")

        try:
            available_themes = self.get_available_themes()
            themes_to_scan = include_themes if include_themes else available_themes

            all_rated: List[Dict[str, Any]] = []

            for theme in themes_to_scan:
                theme_symbols = self.get_symbols_by_theme(theme)
                if not theme_symbols:
                    continue

                # Apply whitelist
                if self._whitelist_enabled and self._whitelist_symbols:
                    theme_symbols = [s for s in theme_symbols if s in self._whitelist_symbols]

                # Filter by liquidity
                liquid_symbols = await self._filter_by_liquidity(theme_symbols, min_liquidity, data_agent)

                # Rank within theme
                ranked = await self._rank_symbols(liquid_symbols, data_agent)

                # Take top N for this theme with ratings
                for rank_idx, (symbol, score) in enumerate(ranked[:top_n]):
                    all_rated.append({
                        "symbol": symbol,
                        "theme": theme,
                        "rating": round(score, 4),
                        "rank": rank_idx + 1,
                    })

            # Sort all by rating descending
            all_rated.sort(key=lambda x: x["rating"], reverse=True)

            # Update internal watchlist and persist to disk
            self._watchlist = all_rated
            self._watchlist_symbols = [r["symbol"] for r in all_rated]
            self._last_discovery = datetime.utcnow().isoformat()
            self._save_watchlist()

            # Build flat symbol list for backward compatibility
            flat_symbols = self._watchlist_symbols

            message = f"Discovered {len(flat_symbols)} symbols from {len(themes_to_scan)} themes (top {top_n} each)."
            payload = {
                "symbols": flat_symbols,
                "rated_symbols": all_rated,
                "count": len(flat_symbols),
                "total_scanned": sum(len(self.get_symbols_by_theme(t)) for t in themes_to_scan),
                "themes_scanned": themes_to_scan,
                "top_n_per_theme": top_n,
                "discovery_timestamp": self._last_discovery,
            }
            logger.info(message)

            report = AgentReport(
                agent_id=self.agent_id,
                status="opportunity",
                message=message,
                payload=payload
            )

            # Publish MARKET_SCANNED event
            try:
                await self.event_bus.publish(Event(
                    event_type=Events.MARKET_SCANNED,
                    data=asdict(report)
                ))
            except Exception as e:
                logger.error(f"Error publishing MARKET_SCANNED event: {e}", exc_info=True)
                raise

            return report

        except Exception as e:
            logger.error(f"Error in discovery scan: {e}", exc_info=True)
            raise

    # ─── Tier 2: Price Monitor (every 15 min) ───────────────────────

    async def refresh_watchlist_prices(self, data_agent=None,
                                       held_symbols: Optional[List[str]] = None) -> AgentReport:
        """
        Tier 2 — Lightweight price refresh for watchlist + held positions.
        
        Fetches only the latest price (no full OHLCV history needed).
        Does NOT re-run news/analysis/strategy.
        
        Args:
            data_agent: DataAgent for fetching current quotes
            held_symbols: Symbols from PortfolioAgent (always included)
        
        Returns:
            AgentReport with price snapshots
        """
        # Merge watchlist + held positions (dedup)
        symbols_to_check = list(self._watchlist_symbols)
        if held_symbols:
            for s in held_symbols:
                if s not in symbols_to_check:
                    symbols_to_check.append(s)

        logger.info(f"[PriceMonitor] Refreshing prices for {len(symbols_to_check)} symbols "
                     f"(watchlist={len(self._watchlist_symbols)}, held={len(held_symbols or [])})")

        if not symbols_to_check:
            return AgentReport(
                agent_id=self.agent_id,
                status="success",
                message="No symbols to monitor.",
                payload={"prices": [], "count": 0}
            )

        prices: List[Dict[str, Any]] = []
        for symbol in symbols_to_check:
            price_data = await self._fetch_quick_quote(symbol, data_agent)
            if price_data:
                prices.append(price_data)

        message = f"Price refresh: {len(prices)} of {len(symbols_to_check)} symbols updated."
        payload = {
            "prices": prices,
            "count": len(prices),
            "symbols_checked": len(symbols_to_check),
            "timestamp": datetime.utcnow().isoformat(),
        }
        logger.info(message)

        report = AgentReport(
            agent_id=self.agent_id,
            status="success",
            message=message,
            payload=payload
        )

        # Publish PRICE_REFRESH_COMPLETE event
        try:
            await self.event_bus.publish(Event(
                event_type=Events.PRICE_REFRESH_COMPLETE,
                data=asdict(report)
            ))
        except Exception as e:
            logger.error(f"Error publishing PRICE_REFRESH_COMPLETE: {e}", exc_info=True)

        return report

    # ─── Internal methods ──────────────────────────────────────────

    async def _fetch_quick_quote(self, symbol: str, data_agent=None) -> Optional[Dict[str, Any]]:
        """Fetch latest price for a single symbol (lightweight)."""
        if not data_agent:
            logger.debug(f"No DataAgent, skipping quote for {symbol}")
            return None
        try:
            report = await data_agent.run(
                symbol=symbol,
                interval="1d",
                use_cache=True,
                emit_events=False
            )
            if report and report.status == "success" and report.payload:
                df_dict = report.payload.get("dataframe", {})
                price, volume, change = self._extract_latest_price(df_dict)
                if price is not None:
                    return {
                        "symbol": symbol,
                        "price": price,
                        "volume": volume,
                        "change_pct": change,
                        "timestamp": datetime.utcnow().isoformat(),
                    }
        except Exception as e:
            logger.debug(f"Quick quote failed for {symbol}: {e}")
        return None

    def _extract_latest_price(self, df_dict) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """Extract latest close price, volume, and daily change from dataframe dict."""
        if not isinstance(df_dict, dict):
            return None, None, None

        prices = []
        volumes = []
        for record in df_dict.values() if isinstance(df_dict, dict) else []:
            if isinstance(record, dict):
                if "close" in record:
                    try:
                        prices.append(float(record["close"]))
                    except (ValueError, TypeError):
                        pass
                if "volume" in record:
                    try:
                        volumes.append(float(record["volume"]))
                    except (ValueError, TypeError):
                        pass

        if not prices:
            return None, None, None

        latest_price = prices[-1]
        latest_volume = volumes[-1] if volumes else None
        change_pct = None
        if len(prices) >= 2 and prices[-2] > 0:
            change_pct = round(((prices[-1] - prices[-2]) / prices[-2]) * 100, 2)

        return latest_price, latest_volume, change_pct

    async def _filter_by_liquidity(self, symbols: List[str], min_liquidity: float, data_agent=None) -> List[str]:
        """Filter symbols by average daily volume."""
        if min_liquidity <= 0:
            return symbols
        if not data_agent:
            logger.warning("DataAgent not provided, skipping liquidity filter")
            return symbols

        liquid_symbols = []
        for symbol in symbols:
            try:
                report = await data_agent.run(
                    symbol=symbol, interval="1d", use_cache=True, emit_events=False
                )
                if report and report.status == "success" and report.payload:
                    df_dict = report.payload.get("dataframe", {})
                    volumes = self._extract_volumes(df_dict)
                    if volumes:
                        avg_vol = sum(volumes) / len(volumes)
                        if avg_vol >= min_liquidity:
                            liquid_symbols.append(symbol)
                        continue
                # Default: include if no data
                liquid_symbols.append(symbol)
            except Exception as e:
                logger.warning(f"Liquidity check failed for {symbol}: {e}")
                liquid_symbols.append(symbol)

        logger.info(f"Liquidity filter: {len(liquid_symbols)}/{len(symbols)} passed")
        return liquid_symbols

    async def _rank_symbols(self, symbols: List[str], data_agent=None) -> List[Tuple[str, float]]:
        """
        Rank symbols by composite score.
        
        Scoring: Technical 30% + Momentum 20% + Value 20% + Trend 20% + Liquidity 10%
        
        Returns:
            List of (symbol, score) tuples sorted descending by score
        """
        if not symbols:
            return []

        if not data_agent:
            return [(s, 0.5) for s in symbols]

        scored: List[Tuple[str, float]] = []

        for symbol in symbols:
            try:
                report = await data_agent.run(
                    symbol=symbol, interval="1d", use_cache=True, emit_events=False
                )
                if not report or report.status != "success":
                    scored.append((symbol, 0.5))
                    continue

                payload = report.payload or {}
                fundamentals = payload.get("fundamentals", {})
                df_dict = payload.get("dataframe", {})

                prices = self._extract_prices(df_dict)
                volumes = self._extract_volumes(df_dict)

                # 1. Technical strength (30%)
                technical_score = self._calc_technical_score(prices)

                # 2. Momentum (20%)
                momentum_score = self._calc_momentum_score(volumes)

                # 3. Value (20%)
                value_score = self._calc_value_score(fundamentals)

                # 4. Trend alignment (20%)
                trend_score = self._calc_trend_score(fundamentals)

                # 5. Liquidity (10%)
                liquidity_score = self._calc_liquidity_score(volumes)

                composite = (
                    technical_score * 0.30 +
                    momentum_score * 0.20 +
                    value_score * 0.20 +
                    trend_score * 0.20 +
                    liquidity_score * 0.10
                )
                scored.append((symbol, composite))

            except Exception as e:
                logger.warning(f"Error scoring {symbol}: {e}")
                scored.append((symbol, 0.5))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    # ─── Score calculation helpers ────────────────────────────────

    def _extract_prices(self, df_dict) -> List[float]:
        prices = []
        if isinstance(df_dict, dict):
            for record in df_dict.values():
                if isinstance(record, dict) and "close" in record:
                    try:
                        prices.append(float(record["close"]))
                    except (ValueError, TypeError):
                        pass
        return prices

    def _extract_volumes(self, df_dict) -> List[float]:
        volumes = []
        if isinstance(df_dict, dict):
            for record in df_dict.values():
                if isinstance(record, dict) and "volume" in record:
                    try:
                        volumes.append(float(record["volume"]))
                    except (ValueError, TypeError):
                        pass
        return volumes

    def _calc_technical_score(self, prices: List[float]) -> float:
        if len(prices) < 20:
            return 0.5
        recent = prices[-5:]
        older = prices[-20:-15]
        if not older:
            return 0.5
        recent_avg = sum(recent) / len(recent)
        older_avg = sum(older) / len(older)
        if older_avg <= 0:
            return 0.5
        momentum = (recent_avg - older_avg) / older_avg
        return min(1.0, max(0.0, (momentum + 0.5) / 1.0))

    def _calc_momentum_score(self, volumes: List[float]) -> float:
        if len(volumes) < 20:
            return 0.5
        recent = volumes[-5:]
        older = volumes[-20:-15]
        if not older:
            return 0.5
        recent_avg = sum(recent) / len(recent)
        older_avg = sum(older) / len(older)
        if older_avg <= 0:
            return 0.5
        ratio = recent_avg / older_avg
        return min(1.0, max(0.0, (ratio - 0.5) / 1.5))

    def _calc_value_score(self, fundamentals: Dict) -> float:
        pe = fundamentals.get("pe_ratio")
        if pe and isinstance(pe, (int, float)) and pe > 0:
            return min(1.0, max(0.0, 1.0 - (pe - 10) / 30))
        return 0.5

    def _calc_trend_score(self, fundamentals: Dict) -> float:
        mc = fundamentals.get("market_cap")
        if mc and isinstance(mc, (int, float)) and mc > 0:
            if 1e9 <= mc <= 1e11:
                return 1.0
            if 5e8 <= mc < 1e9 or 1e11 < mc <= 5e11:
                return 0.7
        return 0.5

    def _calc_liquidity_score(self, volumes: List[float]) -> float:
        if not volumes:
            return 0.5
        avg_vol = sum(volumes) / len(volumes)
        if avg_vol >= 1e7:
            return min(1.0, avg_vol / 1e8)
        return 0.5

    # ─── Utility methods ─────────────────────────────────────────

    def scan_theme(self, theme: str) -> Dict[str, Any]:
        """Detailed scan of a single theme."""
        symbols = self.get_symbols_by_theme(theme)
        return {"theme": theme, "symbols": symbols, "count": len(symbols)}

    def scan_all_themes(self) -> Dict[str, Dict]:
        """Scan all themes and return detail."""
        result = {}
        for theme in self.get_available_themes():
            symbols = self.get_symbols_by_theme(theme)
            result[theme] = {"symbols": symbols, "count": len(symbols)}
        return result

    def validate_symbols(self, symbols: List[str]) -> Dict[str, List[str]]:
        """Validate symbols against universe."""
        all_symbols = set(self.get_all_symbols())
        return {
            "valid": [s for s in symbols if s in all_symbols],
            "invalid": [s for s in symbols if s not in all_symbols],
        }

    def get_stats(self) -> Dict:
        """Get universe statistics."""
        all_symbols = self.get_all_symbols()
        themes = self.get_available_themes()
        return {
            "total_symbols": len(all_symbols),
            "total_themes": len(themes),
            "themes": themes,
            "whitelist_enabled": self._whitelist_enabled,
            "whitelist_count": len(self._whitelist_symbols) if self._whitelist_enabled else 0,
            "watchlist_count": len(self._watchlist),
            "last_discovery": self._last_discovery,
        }

    def __repr__(self) -> str:
        stats = self.get_stats()
        return (f"MarketScannerAgent(symbols={stats['total_symbols']}, "
                f"themes={stats['total_themes']}, watchlist={stats['watchlist_count']})")
