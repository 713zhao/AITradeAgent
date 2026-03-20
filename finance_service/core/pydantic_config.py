"""Pydantic-based configuration with validation and environment variable loading."""
import os
from pathlib import Path
from typing import Dict, Any, Optional, List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class PydanticConfig(BaseSettings):
    """Type-safe configuration with validation using Pydantic."""

    # Core paths
    BASE_DIR: Path = Path(__file__).parent.parent.resolve()
    STORAGE_DIR: Path = BASE_DIR / "storage"
    CACHE_FILE: Path = STORAGE_DIR / "cache.sqlite"
    RUNS_FILE: Path = STORAGE_DIR / "runs.sqlite"

    # Data configuration
    DEFAULT_LOOKBACK_DAYS: int = Field(252, ge=1, description="Default days of historical data to fetch")
    CACHE_TTL_SECONDS: int = Field(3600, ge=0, description="Cache time-to-live in seconds")

    # Risk configuration
    MAX_POSITION_SIZE: float = Field(0.20, gt=0, le=1, description="Max position size as fraction of portfolio")
    MAX_EXPOSURE: float = Field(0.90, gt=0, le=1, description="Maximum total portfolio exposure")
    MAX_DAILY_LOSS: float = Field(0.03, ge=0, le=1, description="Maximum daily loss limit")
    MAX_DRAWDOWN: float = Field(0.10, ge=0, le=1, description="Maximum drawdown limit")
    DEFAULT_RISK_BUDGET: float = Field(0.01, ge=0, le=1, description="Default risk per trade")

    # Trading configuration
    WHITELIST_SYMBOLS: Optional[str] = Field(None, description="Comma-separated whitelist of symbols (None = all)")
    DEFAULT_INITIAL_CASH: float = Field(100000.0, gt=0, description="Starting cash for portfolio")
    TRADE_SLIPPAGE: float = Field(0.0005, ge=0, le=0.1, description="Slippage per trade as fraction")

    # OpenBB configuration
    OPENBB_API_RETRIES: int = Field(3, ge=1, description="Number of retries for OpenBB API calls")
    OPENBB_TIMEOUT: int = Field(30, gt=0, description="Timeout for OpenBB API calls in seconds")

    # Approval configuration
    APPROVAL_TIMEOUT: int = Field(300, ge=0, description="Approval timeout in seconds")
    TELEGRAM_BOT_TOKEN: str = Field("", description="Telegram bot token")
    TELEGRAM_CHAT_ID: str = Field("", description="Telegram chat ID for notifications")
    SLACK_BOT_TOKEN: str = Field("", description="Slack bot token")
    SLACK_CHANNEL: str = Field("", description="Slack channel for notifications")

    # Strategy configuration
    STRATEGY_TYPE: str = Field("baseline_rule", description="Default strategy type")

    # Allow extra fields for future config
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
        validate_assignment=True,
    )

    @field_validator("WHITELIST_SYMBOLS", mode="before")
    @classmethod
    def parse_whitelist(cls, v) -> Optional[List[str]]:
        """Parse whitelist from comma-separated string."""
        if v is None or v == "":
            return None
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            items = [s.strip() for s in v.split(",") if s.strip()]
            return items if items else None
        return v

    def get_whitelist_symbols(self) -> Optional[List[str]]:
        """Get whitelist as a list, or None if no whitelist."""
        return self.WHITELIST_SYMBOLS

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        return self.model_dump()

    def __repr__(self) -> str:
        return f"PydanticConfig(STORAGE_DIR={self.STORAGE_DIR}, MAX_POSITION_SIZE={self.MAX_POSITION_SIZE})"


# Global validated settings instance
settings = PydanticConfig()
