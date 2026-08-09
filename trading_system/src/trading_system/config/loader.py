from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel


class RiskConfig(BaseModel):
    max_position_weight: float = 0.15
    max_positions: int = 12
    min_confidence: float = 0.55
    max_daily_loss_pct: float = 0.03
    cooldown_minutes_after_loss: int = 60
    default_stop_loss_pct: float = 0.08


class LLMConfig(BaseModel):
    enabled: bool = False
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    base_url: str | None = None
    api_key_env: str = "OPENAI_API_KEY"


class BrokerConfig(BaseModel):
    slippage_bps: float = 5.0
    commission_bps: float = 1.0


class AppConfig(BaseModel):
    universe: list[str] = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN"]
    scan_limit: int | None = None
    lookback_days: int = 250
    starting_cash: float = 100_000.0
    db_path: str = "storage/portfolio.sqlite"
    scan_interval_minutes: int = 15
    risk: RiskConfig = RiskConfig()
    llm: LLMConfig = LLMConfig()
    broker: BrokerConfig = BrokerConfig()


def load_config(path: str | Path) -> AppConfig:
    raw = yaml.safe_load(Path(path).read_text()) or {}
    return AppConfig(**raw)
