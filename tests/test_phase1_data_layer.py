"""Phase 1 Data Layer Tests - Provider, Cache, Scanner, Manager"""
import pytest
import tempfile
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from finance_service.core.yaml_config import YAMLConfigEngine
from finance_service.data.yfinance_provider import YfinanceProvider, RateLimitConfig
from finance_service.data.data_cache import DataCache
from finance_service.data.universe_scanner import UniverseScanner
from finance_service.data.data_manager import DataManager


class TestYfinanceProvider:
    """Test yfinance data provider"""
    
    def setup_method(self):
        """Setup for each test"""
        self.config = RateLimitConfig(
            batch_size=5,
            batch_delay_sec=0.1,
            request_jitter_sec=0.01,
            max_retries=2
        )
        self.provider = YfinanceProvider(self.config)
    
    def test_provider_initialization(self):
        """Test provider initializes"""
        assert self.provider is not None
        assert self.provider.config.batch_size == 5
    
    def test_rate_limit_config(self):
        """Test rate limit configuration"""
        assert self.config.max_retries == 2
        assert self.config.backoff_multiplier == 1.5
    
    def test_validate_ohlcv(self):
        """Test OHLCV validation"""
        # Create valid data with proper datetime index
        dates = pd.date_range('2024-01-01', periods=5)
        df_valid = pd.DataFrame({
            'Open': [100.0, 101.0, 102.0, 103.0, 104.0],
            'High': [102.0, 103.0, 104.0, 105.0, 106.0],
            'Low': [99.0, 100.0, 101.0, 102.0, 103.0],
            'Close': [101.0, 102.0, 103.0, 104.0, 105.0],
            'Volume': [1000000, 1100000, 1200000, 1300000, 1400000]
        }, index=dates)
        
        assert self.provider._validate_ohlcv(df_valid) is True
        
        # Test invalid data (zeros)
        df_invalid = pd.DataFrame({
            'Open': [0, 0],
            'High': [0, 0],
            'Low': [0, 0],
            'Close': [0, 0],
            'Volume': [0, 0]
        })
        
        assert self.provider._validate_ohlcv(df_invalid) is False
        
        # Test empty DataFrame
        df_empty = pd.DataFrame()
        assert self.provider._validate_ohlcv(df_empty) is False
    
    def test_provider_stats(self):
        """Test provider statistics"""
        stats = self.provider.get_stats()
        
        assert stats['provider'] == 'yfinance'
        assert 'batch_size' in stats['configuration']
        assert stats['configuration']['batch_size'] == 5


class TestDataCache:
    """Test data caching layer"""
    
    def setup_method(self):
        """Setup for each test"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache = DataCache(
            db_path=str(Path(self.temp_dir.name) / "cache.sqlite"),
            ttl_minutes=1440
        )
    
    def teardown_method(self):
        """Cleanup"""
        self.temp_dir.cleanup()
    
    def test_cache_initialization(self):
        """Test cache initializes"""
        assert self.cache is not None
        assert self.cache.ttl_minutes == 1440
    
    def test_cache_set_and_get(self):
        """Test setting and getting cached data"""
        # Create test data
        df = pd.DataFrame({
            'Open': [100.0, 101.0],
            'High': [102.0, 103.0],
            'Low': [99.0, 100.0],
            'Close': [101.0, 102.0],
            'Volume': [1000000, 1100000]
        }, index=pd.date_range('2024-01-01', periods=2))
        
        # Set cache
        result = self.cache.set("NVDA", df, interval="1d")
        assert result is True
        
        # Get cache
        cached = self.cache.get("NVDA", interval="1d")
        assert cached is not None
        assert len(cached) == 2
    
    def test_cache_miss(self):
        """Test cache miss for uncached symbol"""
        cached = self.cache.get("UNKNOWN", interval="1d")
        assert cached is None
    
    def test_cache_invalidate(self):
        """Test cache invalidation"""
        # Set data
        df = pd.DataFrame({
            'Open': [100.0],
            'High': [102.0],
            'Low': [99.0],
            'Close': [101.0],
            'Volume': [1000000]
        }, index=pd.date_range('2024-01-01', periods=1))
        
        self.cache.set("NVDA", df, interval="1d")
        assert self.cache.get("NVDA", interval="1d") is not None
        
        # Invalidate
        self.cache.invalidate("NVDA")
        assert self.cache.get("NVDA", interval="1d") is None
    
    def test_cache_stats(self):
        """Test cache statistics"""
        df = pd.DataFrame({
            'Open': [100.0],
            'High': [102.0],
            'Low': [99.0],
            'Close': [101.0],
            'Volume': [1000000]
        }, index=pd.date_range('2024-01-01', periods=1))
        
        self.cache.set("NVDA", df, interval="1d")
        
        stats = self.cache.get_stats()
        assert stats['total_candles'] == 1
        assert stats['symbols_cached'] == 1
        assert 'NVDA' in stats['cache_size_symbols']


class TestUniverseScanner:
    """Test universe scanning"""
    
    def setup_method(self):
        """Setup for each test"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create test config
            config_file = temp_path / "finance.yaml"
            config_file.write_text("""
universe:
  themes:
    - name: "AI"
      symbols:
        - NVDA
        - PLTR
    - name: "Semiconductor"
      symbols:
        - TSM
        - QCOM
  all_symbols:
    - NVDA
    - PLTR
    - TSM
    - QCOM
  whitelist:
    enabled: false
    symbols: []
""")
            
            self.config = YAMLConfigEngine(str(temp_path))
        
        self.scanner = UniverseScanner(self.config)
    
    def test_scanner_initialization(self):
        """Test scanner initializes"""
        assert self.scanner is not None
        stats = self.scanner.get_stats()
        assert stats['total_symbols'] == 4
    
    def test_get_all_symbols(self):
        """Test getting all symbols"""
        symbols = self.scanner.get_all_symbols()
        assert len(symbols) == 4
        assert "NVDA" in symbols
    
    def test_get_symbols_by_theme(self):
        """Test getting symbols by theme"""
        symbols = self.scanner.get_symbols_by_theme("AI")
        assert len(symbols) == 2
        assert "NVDA" in symbols
        assert "PLTR" in symbols
    
    def test_get_available_themes(self):
        """Test getting available themes"""
        themes = self.scanner.get_available_themes()
        assert "AI" in themes
        assert "Semiconductor" in themes
    
    def test_scan_universe(self):
        """Test scanning universe"""
        symbols = self.scanner.scan_universe()
        assert len(symbols) == 4
    
    def test_scan_specific_themes(self):
        """Test scanning specific themes"""
        symbols = self.scanner.scan_universe(include_themes=["AI"])
        assert len(symbols) == 2
    
    def test_validate_symbols(self):
        """Test symbol validation"""
        result = self.scanner.validate_symbols(["NVDA", "UNKNOWN"])
        assert "NVDA" in result["valid"]
        assert "UNKNOWN" in result["invalid"]


class TestDataManager:
    """Test data manager orchestration"""
    
    def setup_method(self):
        """Setup for each test"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create test config
            config_file = temp_path / "finance.yaml"
            config_file.write_text("""
universe:
  themes:
    - name: "AI"
      symbols:
        - NVDA
        - PLTR
  all_symbols:
    - NVDA
    - PLTR
  whitelist:
    enabled: false
    symbols: []

risk:
  max_position_size_pct: 20

data:
  cache_ttl_minutes: 1440
  batch_size: 10
  batch_delay_sec: 0.5
  request_jitter_sec: 0.5
  backoff:
    initial_wait_sec: 1
    max_wait_sec: 30
    multiplier: 2.0

performance:
  api_retries: 3
  api_timeout_sec: 30
""")
            
            self.config = YAMLConfigEngine(str(temp_path))
        
        # Create manager with temp storage
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage_path = Path(self.temp_dir.name)
        
        self.manager = DataManager(self.config)
    
    def teardown_method(self):
        """Cleanup"""
        self.temp_dir.cleanup()
    
    def test_manager_initialization(self):
        """Test manager initializes"""
        assert self.manager is not None
        assert self.manager.config is not None
        assert self.manager.provider is not None
        assert self.manager.cache is not None
        assert self.manager.scanner is not None
    
    def test_get_universe(self):
        """Test getting trading universe"""
        symbols = self.manager.get_universe()
        assert len(symbols) == 2
        assert "NVDA" in symbols or "PLTR" in symbols
    
    def test_get_universe_by_theme(self):
        """Test getting universe by theme"""
        symbols = self.manager.get_universe(theme="AI")
        assert len(symbols) == 2
    
    def test_get_universe_info(self):
        """Test getting universe information"""
        info = self.manager.get_universe_info()
        assert 'universe' in info
        assert 'stats' in info
        assert 'all_themes' in info
    
    def test_manager_stats(self):
        """Test manager statistics"""
        stats = self.manager.get_stats()
        assert 'provider' in stats
        assert 'cache' in stats
        assert 'universe' in stats


class TestPhase1Integration:
    """Integration tests for Phase 1 data layer"""
    
    def test_cache_with_provider(self):
        """Test cache integration with provider"""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = str(Path(temp_dir) / "cache.sqlite")
            cache = DataCache(cache_path)
            
            # Create test data
            df = pd.DataFrame({
                'Open': [100.0, 101.0],
                'High': [102.0, 103.0],
                'Low': [99.0, 100.0],
                'Close': [101.0, 102.0],
                'Volume': [1000000, 1100000]
            }, index=pd.date_range('2024-01-01', periods=2))
            
            # "Fetch" and cache
            cache.set("NVDA", df, interval="1d")
            
            # Verify cache hit
            cached = cache.get("NVDA", interval="1d")
            assert cached is not None
            assert len(cached) == 2
    
    def test_data_manager_flow(self):
        """Test complete data manager workflow"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create config
            config_file = temp_path / "finance.yaml"
            config_file.write_text("""
universe:
  themes:
    - name: "Test"
      symbols:
        - NVDA
  all_symbols:
    - NVDA
  whitelist:
    enabled: false
    symbols: []

risk:
  max_position_size_pct: 20

data:
  cache_ttl_minutes: 1440
  batch_size: 10
  batch_delay_sec: 0.5
  request_jitter_sec: 0.5
  backoff:
    initial_wait_sec: 1
    max_wait_sec: 30
    multiplier: 2.0

performance:
  api_retries: 3
  api_timeout_sec: 30
""")
            
            config = YAMLConfigEngine(str(temp_path))
            manager = DataManager(config)
            
            # Check universe
            universe = manager.get_universe()
            assert "NVDA" in universe


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
