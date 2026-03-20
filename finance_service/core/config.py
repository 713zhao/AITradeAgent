"""Configuration management for Finance Agent

This module provides the Config class with type-safe, validated settings
backed by Pydantic. All configuration values are loaded from environment
variables with sensible defaults and validation.
"""
import os
from typing import Dict, Any, Optional
from pathlib import Path

# Import validated Pydantic settings
from .pydantic_config import settings as _pydantic_settings


class Config:
    """Central configuration for Finance Agent

    Class attributes are populated from validated Pydantic settings.
    All values have sensible defaults and are validated at startup.
    """

    # Paths - from validated settings
    BASE_DIR = _pydantic_settings.BASE_DIR
    STORAGE_DIR = _pydantic_settings.STORAGE_DIR
    CACHE_FILE = _pydantic_settings.CACHE_FILE
    RUNS_FILE = _pydantic_settings.RUNS_FILE

    # Data configuration
    DEFAULT_LOOKBACK_DAYS = _pydantic_settings.DEFAULT_LOOKBACK_DAYS
    CACHE_TTL_SECONDS = _pydantic_settings.CACHE_TTL_SECONDS

    # Risk configuration
    MAX_POSITION_SIZE = _pydantic_settings.MAX_POSITION_SIZE
    MAX_EXPOSURE = _pydantic_settings.MAX_EXPOSURE
    MAX_DAILY_LOSS = _pydantic_settings.MAX_DAILY_LOSS
    MAX_DRAWDOWN = _pydantic_settings.MAX_DRAWDOWN
    DEFAULT_RISK_BUDGET = _pydantic_settings.DEFAULT_RISK_BUDGET

    # Trading configuration
    WHITELIST_SYMBOLS = _pydantic_settings.WHITELIST_SYMBOLS
    DEFAULT_INITIAL_CASH = _pydantic_settings.DEFAULT_INITIAL_CASH
    TRADE_SLIPPAGE = _pydantic_settings.TRADE_SLIPPAGE

    # OpenBB configuration
    OPENBB_API_RETRIES = _pydantic_settings.OPENBB_API_RETRIES
    OPENBB_TIMEOUT = _pydantic_settings.OPENBB_TIMEOUT

    # Approval configuration
    APPROVAL_TIMEOUT = _pydantic_settings.APPROVAL_TIMEOUT
    TELEGRAM_BOT_TOKEN = _pydantic_settings.TELEGRAM_BOT_TOKEN
    TELEGRAM_CHAT_ID = _pydantic_settings.TELEGRAM_CHAT_ID
    SLACK_BOT_TOKEN = _pydantic_settings.SLACK_BOT_TOKEN
    SLACK_CHANNEL = _pydantic_settings.SLACK_CHANNEL

    # Strategy configuration
    STRATEGY_TYPE = _pydantic_settings.STRATEGY_TYPE

    @classmethod
    def validate(cls) -> bool:
        """Validate essential configuration.

        Note: Validation is already performed by Pydantic during settings load.
        This method exists for backward compatibility and always returns True
        if the module imported successfully (meaning config is valid).
        """
        # If we got here, Pydantic validation passed
        return True

    @classmethod
    def load_config(cls) -> Dict[str, Any]:
        """Load configuration as a dictionary of all uppercase class attributes"""
        return _pydantic_settings.to_dict()

    @classmethod
    def ensure_storage_dirs(cls) -> None:
        """Ensure storage directories exist"""
        cls.STORAGE_DIR.mkdir(parents=True, exist_ok=True)


# Ensure storage directory exists on import
Config.ensure_storage_dirs()
