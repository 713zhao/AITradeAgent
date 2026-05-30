"""Type-safe configuration with validation.

Now loads defaults from YAML (config/config.yaml) with environment overrides.
Secrets still loaded from .env.
"""
import os
from pathlib import Path
from typing import Dict, Any, Optional, List
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from ..core.yaml_config import get_config_engine


class PydanticConfig(BaseSettings):
    """Type-safe configuration backed by YAML + environment variables."""

    # Core paths (from YAML or defaults)
    BASE_DIR: Path = Path(__file__).parent.parent.parent.resolve()
    STORAGE_DIR: Path = BASE_DIR / "storage"
    CACHE_FILE: Path = STORAGE_DIR / "cache.sqlite"
    RUNS_FILE: Path = STORAGE_DIR / "runs.sqlite"

    # Data configuration
    DEFAULT_LOOKBACK_DAYS: int = Field(252, ge=1)
    CACHE_TTL_SECONDS: int = Field(3600, ge=0)
    OPENBB_API_RETRIES: int = Field(3, ge=1)
    OPENBB_TIMEOUT: int = Field(30, gt=0)

    # Risk configuration
    MAX_POSITION_SIZE: float = Field(0.20, gt=0, le=1)
    MAX_EXPOSURE: float = Field(0.90, gt=0, le=1)
    MAX_DAILY_LOSS: float = Field(0.03, ge=0, le=1)
    MAX_DRAWDOWN: float = Field(0.10, ge=0, le=1)
    DEFAULT_RISK_BUDGET: float = Field(0.01, ge=0, le=1)

    # Trading configuration
    WHITELIST_SYMBOLS: Optional[List[str]] = Field(None)
    DEFAULT_INITIAL_CASH: float = Field(100000.0, gt=0)
    TRADE_SLIPPAGE: float = Field(0.0005, ge=0, le=0.1)

    # Approval configuration
    APPROVAL_TIMEOUT: int = Field(300, ge=0)
    TELEGRAM_BOT_TOKEN: str = Field("")
    TELEGRAM_CHAT_ID: str = Field("")
    TELEGRAM_MESSAGE_THREAD_ID: Optional[int] = Field(None)
    SLACK_BOT_TOKEN: str = Field("")
    SLACK_CHANNEL: str = Field("")

    # Strategy configuration
    STRATEGY_TYPE: str = Field("baseline_rule")

    # LLM configuration (maps to YAML llm.*)
    LLM_ENABLED: bool = Field(False)
    LLM_PROVIDER: str = Field("openrouter")
    LLM_API_KEY_ENV: str = Field("OPENROUTER_API_KEY")
    LLM_BASE_URL: Optional[str] = Field(None)
    LLM_DEFAULT_MODEL: str = Field("anthropic/claude-3.7-sonnet")
    LLM_TEMPERATURE: float = Field(0.3, ge=0.0, le=2.0)
    LLM_MODULE_MARKET_REGIME_ENABLED: bool = Field(False)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        validate_assignment=True,
    )

    @field_validator("WHITELIST_SYMBOLS", mode="before")
    @classmethod
    def parse_whitelist(cls, v) -> Optional[List[str]]:
        if v is None or v == "":
            return None
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            items = [s.strip() for s in v.split(",") if s.strip()]
            return items if items else None
        return v

    @field_validator("TELEGRAM_MESSAGE_THREAD_ID", mode="before")
    @classmethod
    def parse_thread_id(cls, v) -> Optional[int]:
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        return int(v)

    @classmethod
    @lru_cache()
    def _load_yaml_config(cls) -> Dict[str, Any]:
        """Load configuration from YAML file (cached)"""
        try:
            engine = get_config_engine()
            raw = engine.raw_config
            return raw
        except Exception as e:
            logger.warning(f"Failed to load YAML config: {e}")
            return {}

    @classmethod
    def from_yaml(cls):
        """Create config instance populated from YAML + env overrides"""
        yaml_config = cls._load_yaml_config()
        app_cfg = yaml_config.get("app", {})
        finance_cfg = yaml_config.get("finance", {})
        llm_cfg = yaml_config.get("llm", {})

        # Build field values from YAML
        values = {
            # Data
            "DEFAULT_LOOKBACK_DAYS": finance_cfg.get("data", {}).get("default_lookback_days", 252),
            "CACHE_TTL_SECONDS": finance_cfg.get("data", {}).get("cache_ttl_seconds", 3600),
            "OPENBB_API_RETRIES": finance_cfg.get("data", {}).get("api_retries", 3),
            "OPENBB_TIMEOUT": finance_cfg.get("data", {}).get("timeout", 30),
            # Risk
            "MAX_POSITION_SIZE": finance_cfg.get("risk", {}).get("policy", {}).get("max_position_size_pct", 20) / 100,
            "MAX_EXPOSURE": finance_cfg.get("risk", {}).get("policy", {}).get("max_exposure_pct", 90) / 100,
            "MAX_DAILY_LOSS": finance_cfg.get("risk", {}).get("policy", {}).get("max_daily_loss_pct", 3) / 100,
            "MAX_DRAWDOWN": finance_cfg.get("risk", {}).get("policy", {}).get("max_drawdown_pct", 10) / 100,
            "DEFAULT_RISK_BUDGET": finance_cfg.get("risk", {}).get("policy", {}).get("default_risk_budget_pct", 1) / 100,
            # Portfolio
            "DEFAULT_INITIAL_CASH": finance_cfg.get("portfolio", {}).get("initial_cash", 100000.0),
            "TRADE_SLIPPAGE": finance_cfg.get("portfolio", {}).get("trade_slippage", 0.0005),
            # Strategy
            "STRATEGY_TYPE": finance_cfg.get("strategy", {}).get("type", "baseline_rule"),
            # Execution
            # Scheduling
            # Notifications (TELEGRAM_BOT_TOKEN read from .env only)
            "TELEGRAM_CHAT_ID": finance_cfg.get("notifications", {}).get("telegram", {}).get("chat_id", ""),
            "TELEGRAM_MESSAGE_THREAD_ID": finance_cfg.get("notifications", {}).get("telegram", {}).get("message_thread_id"),
            "SLACK_BOT_TOKEN": finance_cfg.get("notifications", {}).get("slack", {}).get("webhook_url", ""),
            "SLACK_CHANNEL": finance_cfg.get("notifications", {}).get("slack", {}).get("channel", ""),
            # LLM
            "LLM_ENABLED": llm_cfg.get("enabled", False),
            "LLM_PROVIDER": llm_cfg.get("provider", "openrouter"),
            "LLM_API_KEY_ENV": llm_cfg.get("api_key_env", "OPENROUTER_API_KEY"),
            "LLM_BASE_URL": llm_cfg.get("base_url"),
            "LLM_DEFAULT_MODEL": llm_cfg.get("model", "anthropic/claude-3.7-sonnet"),
            "LLM_TEMPERATURE": llm_cfg.get("temperature", 0.3),
            "LLM_MODULE_MARKET_REGIME_ENABLED": llm_cfg.get("modules", {}).get("market_regime", {}).get("enabled", False),
        }

        # Create instance with YAML values, then env overrides via BaseSettings
        return cls(**values)

    def get_whitelist_symbols(self) -> Optional[List[str]]:
        return self.WHITELIST_SYMBOLS

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

    def __repr__(self) -> str:
        return f"PydanticConfig(STORAGE_DIR={self.STORAGE_DIR}, LLM_ENABLED={self.LLM_ENABLED})"


# Global instance (replaces old `settings`)
@lru_cache()
def settings() -> PydanticConfig:
    """Get global settings singleton (cached)"""
    return PydanticConfig.from_yaml()


# Backward compatibility: allow old imports to work
# This ensures existing code using `from finance_service.core.pydantic_config import settings` still works
# but now includes YAML loading.
