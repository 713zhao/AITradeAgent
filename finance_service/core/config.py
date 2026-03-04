"""Configuration management for Finance Service"""
import os
from pathlib import Path
from typing import Optional

class Config:
    """Central configuration for Finance Agent"""
    
    # Paths
    BASE_DIR = Path(__file__).parent.parent
    STORAGE_DIR = BASE_DIR / "storage"
    CACHE_FILE = STORAGE_DIR / "cache.sqlite"
    RUNS_FILE = STORAGE_DIR / "runs.sqlite"
    
    # Ensure storage directory exists
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    
    # Data configuration
    DEFAULT_LOOKBACK_DAYS = 252  # 1 year
    CACHE_TTL_SECONDS = 3600  # 1 hour
    
    # Risk configuration (defaults)
    MAX_POSITION_SIZE = 0.20  # 20% of portfolio
    MAX_EXPOSURE = 0.90  # 90% total exposure
    MAX_DAILY_LOSS = 0.03  # 3% daily stop loss
    MAX_DRAWDOWN = 0.10  # 10% drawdown stop loss
    DEFAULT_RISK_BUDGET = 0.01  # 1% per trade
    
    # Trading configuration
    WHITELIST_SYMBOLS = None  # None = allow any; set to list for restrictions
    DEFAULT_INITIAL_CASH = 100000  # $100k starting capital
    TRADE_SLIPPAGE = 0.0005  # 0.05% slippage
    
    # OpenBB configuration
    OPENBB_API_RETRIES = 3
    OPENBB_TIMEOUT = 30  # seconds
    
    # Approval configuration
    APPROVAL_TIMEOUT = 300  # 5 minutes
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
    SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
    SLACK_CHANNEL = os.getenv("SLACK_CHANNEL", "")
    
    # Strategy configuration
    STRATEGY_TYPE = os.getenv("STRATEGY_TYPE", "baseline_rule")
    
    @classmethod
    def validate(cls) -> bool:
        """Validate essential configuration"""
        if not cls.OPENBB_API_RETRIES > 0:
            raise ValueError("OPENBB_API_RETRIES must be > 0")
        if not (0 < cls.MAX_POSITION_SIZE < 1):
            raise ValueError("MAX_POSITION_SIZE must be between 0 and 1")
        return True
