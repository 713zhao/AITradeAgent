"""Universe Scanner - Select symbols based on themes from config"""
import logging
from typing import List, Dict, Optional, Set
from finance_service.core.yaml_config import YAMLConfigEngine

logger = logging.getLogger(__name__)


class UniverseScanner:
    """Select trading universe based on themes from configuration"""
    
    def __init__(self, config_engine: YAMLConfigEngine):
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
    
    def scan_universe(self, include_themes: Optional[List[str]] = None) -> List[str]:
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
        
        result = sorted(list(symbols))
        logger.info(f"Universe scan complete: {len(result)} symbols")
        
        return result
    
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
