import os
from pathlib import Path
from typing import Optional, List, Dict, Any
import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, model_validator

class _Config(BaseSettings):
    """Central configuration for Finance Agent"""
    
    # Paths
    BASE_DIR: Path = Path(__file__).parent.parent
    STORAGE_DIR: Path = Field(default_factory=lambda: Path(__file__).parent.parent / "storage")
    CACHE_FILE: Path = Field(default_factory=lambda: Path(__file__).parent.parent / "storage" / "cache.sqlite")
    RUNS_FILE: Path = Field(default_factory=lambda: Path(__file__).parent.parent / "storage" / "runs.sqlite")
    
    # Data configuration
    DEFAULT_LOOKBACK_DAYS: int = 252
    CACHE_TTL_SECONDS: int = 3600
    
    # Risk configuration (defaults)
    MAX_POSITION_SIZE: float = Field(0.20, gt=0, le=1.0)
    MAX_EXPOSURE: float = Field(0.90, gt=0, le=1.0)
    MAX_DAILY_LOSS: float = Field(0.03, gt=0, lt=1.0)
    MAX_DRAWDOWN: float = Field(0.10, gt=0, lt=1.0)
    DEFAULT_RISK_BUDGET: float = 0.01
    
    # Trading configuration
    WHITELIST_SYMBOLS: Optional[List[str]] = None
    DEFAULT_INITIAL_CASH: float = 100000.0
    TRADE_SLIPPAGE: float = 0.0005
    
    # OpenBB configuration
    OPENBB_API_RETRIES: int = Field(3, gt=0)
    OPENBB_TIMEOUT: int = 30
    
    # Approval configuration
    APPROVAL_TIMEOUT: int = 300
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""
    SLACK_BOT_TOKEN: str = ""
    SLACK_CHANNEL: str = ""
    
    # Strategy configuration
    STRATEGY_TYPE: str = "baseline_rule"
    
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8", 
        extra="ignore"
    )

    @model_validator(mode='after')
    def validate_setup(self) -> '_Config':
        # Ensure storage directory exists
        self.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        return self

    def load_config(self) -> Dict[str, Any]:
        """Load YAML configuration, apply updates, and return agent config dict."""
        yaml_path = self.BASE_DIR.parent / "config" / "finance.yaml"
        yaml_config = {}
        
        if yaml_path.exists():
            with open(yaml_path, 'r') as f:
                yaml_config = yaml.safe_load(f) or {}
                
            # Update risk parameters from yaml if present
            if "risk" in yaml_config:
                risk = yaml_config["risk"]
                if "max_position_size_pct" in risk:
                    self.MAX_POSITION_SIZE = risk["max_position_size_pct"] / 100.0
                if "max_exposure_pct" in risk:
                    self.MAX_EXPOSURE = risk["max_exposure_pct"] / 100.0
                if "max_daily_loss_pct" in risk:
                    self.MAX_DAILY_LOSS = risk["max_daily_loss_pct"] / 100.0
                if "max_drawdown_pct" in risk:
                    self.MAX_DRAWDOWN = risk["max_drawdown_pct"] / 100.0
                if "default_risk_budget_pct" in risk:
                    self.DEFAULT_RISK_BUDGET = risk["default_risk_budget_pct"] / 100.0
            
            # Update portfolio parameters
            if "portfolio" in yaml_config:
                if "initial_cash" in yaml_config["portfolio"]:
                    self.DEFAULT_INITIAL_CASH = float(yaml_config["portfolio"]["initial_cash"])
                    
        # Construct agent configurations based on yaml or env
        # This matches what MainOrchestratorAgent expects in app.py
        agent_configs = {
            "telegram_agent": {
                "telegram_bot_token": self.TELEGRAM_BOT_TOKEN,
                "telegram_chat_id": self.TELEGRAM_CHAT_ID
            },
            "scheduler_agent": {},
            "market_scanner": yaml_config.get("universe", {}),
            "data_agent": yaml_config.get("data", {}),
            "news_agent": {},
            "analysis_agent": {},
            "strategy_agent": yaml_config.get("strategy", {}),
            "risk_agent": yaml_config.get("risk", {}),
            "execution_agent": {},
            "learning_agent": {},
            "portfolio_agent": yaml_config.get("portfolio", {"initial_cash": self.DEFAULT_INITIAL_CASH})
        }
        
        return agent_configs

    def validate(self, *args, **kwargs) -> bool:
        """Mock validate method for backwards compatibility."""
        return True

Config = _Config()
