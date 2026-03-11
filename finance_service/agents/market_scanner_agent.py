"""Universe Scanner - Select symbols based on themes from config"""
import logging
from typing import List, Dict, Optional, Set
from finance_service.core.yaml_config import YAMLConfigEngine
from finance_service.agents.agent_interface import Agent, AgentReport
from finance_service.core.events import EventType

logger = logging.getLogger(__name__)


class MarketScannerAgent(Agent):
    """Market Scanner Agent - Continuously discovers promising stocks."""

    @property
    def agent_id(self) -> str:
        return "market_scanner_agent"

    @property
    def goal(self) -> str:
        return "Continuously discover promising stocks based on themes, liquidity, and ranking criteria."

    
    def __init__(self, config_engine: YAMLConfigEngine): # type: ignore
        self.config = config_engine
        self._whitelist_enabled = self.config.get("finance", "universe/whitelist/enabled", default=False)
        self._whitelist_symbols = set(self.config.get("finance", "universe/whitelist/symbols", default=[]))
        
        logger.info(f"UniverseScanner initialized (whitelist_enabled={self._whitelist_enabled})")
    
    def get_all_symbols(self) -> List[str]:
        """Get all configured symbols"""
        symbols = self.config.get("finance", "universe/all_symbols", default=[])
        return list(set(symbols))  # Remove duplicates
    
    def get_symbols_by_theme(self, theme: str) -> List[str]:
        """
        Get symbols for a specific theme
        
        Args:
            theme: Theme name (e.g., "AI", "Semiconductor")
        
        Returns:
            List of symbols
        """
        themes = self.config.get("finance", "universe/themes", default=[])
        
        for t in themes:
            if isinstance(t, dict) and t.get("name", "").lower() == theme.lower():
                return list(set(t.get("symbols", [])))
        
        logger.warning(f"Theme '{theme}' not found")
        return []
    
    def get_available_themes(self) -> List[str]:
        """Get all available themes"""
        themes = self.config.get("finance", "universe/themes", default=[])
        return [t.get("name", "") for t in themes if isinstance(t, dict)]
    
    async def run(self, include_themes: Optional[List[str]] = None, 
                  min_liquidity: float = 0.0, 
                  limit: int = 10) -> Optional[AgentReport]:
        """
        Executes the market scanning logic to discover promising stocks.
        """
        logger.info(f"Running market scan with themes={include_themes}, min_liquidity={min_liquidity}, limit={limit}")
        
        # 1. Scan and filter by theme (existing logic)
        candidate_symbols = self._scan_by_themes(include_themes)

        # 2. Filter by liquidity (placeholder for now)
        liquid_symbols = await self._filter_by_liquidity(candidate_symbols, min_liquidity)

        # 3. Rank candidate symbols (placeholder for now)
        ranked_symbols = await self._rank_symbols(liquid_symbols)
        
        # 4. Apply a limit to the results
        final_selection = ranked_symbols[:limit]

        message = f"Discovered {len(final_selection)} promising symbols."
        payload = {"symbols": final_selection, "count": len(final_selection)}
        logger.info(message)
        
        return AgentReport(
            agent_id=self.agent_id,
            status="opportunity",
            message=message,
            payload=payload
        )
        """
        Scan and return trading universe
        
        Args:
            include_themes: Specific themes to include (None = all themes)
        
        Returns:
            List of symbols
        """
        symbols: Set[str] = set()
        available_themes = self.get_available_themes()
        
        # Select themes
        themes_to_scan = include_themes if include_themes else available_themes
        
        for theme in themes_to_scan:
            theme_symbols = self.get_symbols_by_theme(theme)
            symbols.update(theme_symbols)
            logger.debug(f"Added {len(theme_symbols)} symbols from theme '{theme}'")
        
        # Apply whitelist if enabled
        if self._whitelist_enabled and self._whitelist_symbols:
            symbols = symbols.intersection(self._whitelist_symbols)
            logger.info(f"Applied whitelist: {len(symbols)} symbols after filtering")
        
        return sorted(list(symbols))

    def _scan_by_themes(self, include_themes: Optional[List[str]]) -> List[str]:
        symbols: Set[str] = set()
        available_themes = self.get_available_themes()

        themes_to_scan = include_themes if include_themes else available_themes

        for theme in themes_to_scan:
            theme_symbols = self.get_symbols_by_theme(theme)
            symbols.update(theme_symbols)
            logger.debug(f"Added {len(theme_symbols)} symbols from theme '{theme}'")

        if self._whitelist_enabled and self._whitelist_symbols:
            symbols = symbols.intersection(self._whitelist_symbols)
            logger.info(f"Applied whitelist: {len(symbols)} symbols after filtering")

        return sorted(list(symbols))

    async def _filter_by_liquidity(self, symbols: List[str], min_liquidity: float) -> List[str]:
        """
        Placeholder for liquidity filtering logic.
        In a real scenario, this would fetch market data to determine liquidity.
        """
        if min_liquidity > 0:
            logger.info(f"Applying liquidity filter (min_liquidity={min_liquidity})... (Skipped for now)")
            # TODO: Implement actual liquidity check (e.g., average daily volume)
            pass
        return symbols  # Return all symbols for now

    async def _rank_symbols(self, symbols: List[str]) -> List[str]:
        """
        Placeholder for symbol ranking logic.
        In a real scenario, this would use various criteria to rank symbols.
        """
        logger.info("Ranking symbols... (Skipped for now)")
        # TODO: Implement actual ranking logic (e.g., based on recent performance, news sentiment, etc.)
        return symbols  # Return symbols as-is for now

    def __repr__(self) -> str:
        stats = self.get_stats()
        return f"MarketScannerAgent(symbols={stats['total_symbols']}, themes={stats['total_themes']})"
    
    def scan_theme(self, theme: str) -> Dict[str, List[str]]:
        """
        Detailed scan of a single theme
        
        Returns:
            {
                "theme": "AI",
                "symbols": ["NVDA", "PLTR", ...],
                "count": 5
            }
        """
        symbols = self.get_symbols_by_theme(theme)
        
        return {
            "theme": theme,
            "symbols": symbols,
            "count": len(symbols)
        }
    
    def scan_all_themes(self) -> Dict[str, Dict]:
        """
        Scan all themes and return detailed info
        
        Returns:
            {
                "AI": {"symbols": [...], "count": 5},
                "Semiconductor": {"symbols": [...], "count": 5},
                ...
            }
        """
        result = {}
        
        for theme in self.get_available_themes():
            symbols = self.get_symbols_by_theme(theme)
            result[theme] = {
                "symbols": symbols,
                "count": len(symbols)
            }
        
        total_symbols = sum(r["count"] for r in result.values())
        logger.info(f"All themes scanned: {len(result)} themes, {total_symbols} total symbols")
        
        return result
    
    def validate_symbols(self, symbols: List[str]) -> Dict[str, List[str]]:
        """
        Validate symbols against universe
        
        Returns:
            {
                "valid": [...],
                "invalid": [...]
            }
        """
        all_symbols = set(self.get_all_symbols())
        
        valid = [s for s in symbols if s in all_symbols]
        invalid = [s for s in symbols if s not in all_symbols]
        
        return {
            "valid": valid,
            "invalid": invalid
        }
    
    def get_stats(self) -> Dict:
        """Get universe statistics"""
        all_symbols = self.get_all_symbols()
        themes = self.get_available_themes()
        
        return {
            "total_symbols": len(all_symbols),
            "total_themes": len(themes),
            "themes": themes,
            "whitelist_enabled": self._whitelist_enabled,
            "whitelist_count": len(self._whitelist_symbols) if self._whitelist_enabled else 0
        }
    
    def __repr__(self) -> str:
        stats = self.get_stats()
        return f"UniverseScanner(symbols={stats['total_symbols']}, themes={stats['total_themes']})"
