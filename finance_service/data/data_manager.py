"""Data Manager - orchestrates data fetching, caching, and universe scanning"""
import logging
from typing import Dict, List, Optional
from pathlib import Path

from finance_service.core.yaml_config import YAMLConfigEngine
from finance_service.data.yfinance_provider import YfinanceProvider, RateLimitConfig
from finance_service.data.data_cache import DataCache
from finance_service.data.universe_scanner import UniverseScanner

logger = logging.getLogger(__name__)


class DataManager:
    """Orchestrates data layer components: provider, cache, scanner."""
    
    def __init__(self, config: YAMLConfigEngine, storage_path: Optional[Path] = None):
        self.config = config
        
        # Determine storage path
        if storage_path is None:
            storage_path = Path(__file__).parent.parent / "storage" / "data"
        storage_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize components
        rate_limit_config = RateLimitConfig(
            batch_size=config.get("data", "batch_size", default=10),
            batch_delay_sec=config.get("data", "batch_delay_sec", default=0.5),
            request_jitter_sec=config.get("data", "request_jitter_sec", default=0.1),
            max_retries=config.get("performance", "api_retries", default=3),
        )
        self.provider = YfinanceProvider(rate_limit_config)
        
        cache_db = storage_path / "data_cache.sqlite"
        ttl_minutes = config.get("data", "cache_ttl_minutes", default=1440)
        self.cache = DataCache(str(cache_db), ttl_minutes=ttl_minutes)
        
        self.scanner = UniverseScanner(config)
        
        logger.info("DataManager initialized")
    
    def get_universe(self, theme: Optional[str] = None) -> List[str]:
        """Get list of symbols to trade."""
        if theme:
            return self.scanner.get_symbols_by_theme(theme)
        return self.scanner.get_all_symbols()
    
    def get_universe_info(self) -> Dict:
        """Get detailed information about the universe."""
        all_symbols = self.scanner.get_all_symbols()
        themes = self.scanner.get_available_themes()
        theme_symbols = {}
        for theme in themes:
            theme_symbols[theme] = self.scanner.get_symbols_by_theme(theme)
        
        return {
            "universe": {
                "all_symbols": all_symbols,
                "themes": theme_symbols,
            },
            "stats": self.scanner.get_stats(),
            "all_themes": themes,
        }
    
    def get_stats(self) -> Dict:
        """Get comprehensive statistics about data layer."""
        return {
            "universe": {
                "total_symbols": len(self.scanner.get_all_symbols()),
                "themes": self.scanner.get_available_themes(),
                "watchlist_count": len(self.scanner.get_watchlist()),
            },
            "provider": self.provider.get_stats(),
            "cache": self.cache.get_stats(),
            "scanner": self.scanner.get_stats(),
        }
