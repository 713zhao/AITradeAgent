"""CLI entrypoint. Usage:

  python -m trading_system_v3.main --config config.yaml --once --bypass-market-hours
  python -m trading_system_v3.main --config config.yaml --loop
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os

from trading_system_v3.actors.learning_actor import LearningActor
from trading_system_v3.actors.risk_actor import RiskActor, RiskPolicy
from trading_system_v3.actors.strategy_actor import StrategyActor
from trading_system_v3.broker.paper_broker import PaperBroker
from trading_system_v3.config.loader import AppConfig, load_config
from trading_system_v3.core.market_hours import is_market_open
from trading_system_v3.core.models import ExecutionResult, RiskDecision, TradeProposal
from trading_system_v3.data.provider import YFinanceProvider
from trading_system_v3.llm.client import OpenAICompatibleClient
from trading_system_v3.orchestrator import Orchestrator
from trading_system_v3.pipeline.data_stage import DataStage
from trading_system_v3.pipeline.execution_stage import ExecutionStage
from trading_system_v3.pipeline.portfolio_stage import PortfolioStage, PortfolioStore
from trading_system_v3.pipeline.scanner_stage import ScannerStage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("trading_system_v3.main")


def build_orchestrator(config_path: str) -> Orchestrator:
    cfg = load_config(config_path)

    llm_client = None
    if cfg.llm.enabled:
        api_key = os.environ.get(cfg.llm.api_key_env)
        if not api_key:
            logger.warning("LLM enabled but %s not set; falling back to rule strategy", cfg.llm.api_key_env)
        else:
            llm_client = OpenAICompatibleClient(api_key=api_key, model=cfg.llm.model, base_url=cfg.llm.base_url)

    scanner = ScannerStage(cfg.universe, limit=cfg.scan_limit)
    data_stage = DataStage(YFinanceProvider())

    strategy_actor = StrategyActor(memory_db_path=cfg.strategy_memory_db_path, llm_client=llm_client)
    risk_actor = RiskActor(memory_db_path=cfg.risk_memory_db_path, policy=RiskPolicy(**cfg.risk.model_dump()))
    learning_actor = LearningActor(memory_db_path=cfg.learning_memory_db_path, llm_client=llm_client)
    for actor in (strategy_actor, risk_actor, learning_actor):
        actor.start()

    broker = PaperBroker(**cfg.broker.model_dump())
    execution_stage = ExecutionStage(broker)
    store = PortfolioStore(cfg.db_path, starting_cash=cfg.starting_cash)
    portfolio_stage = PortfolioStage(store)

    return Orchestrator(
        scanner=scanner, data=data_stage, strategy=strategy_actor, risk=risk_actor,
        execution=execution_stage, portfolio=portfolio_stage, learning=learning_actor,
        lookback_days=cfg.lookback_days,
    )


def _summarize(results: list[dict]) -> None:
    for r in results:
        symbol = r["symbol"]
        if "error" in r:
            logger.info("%s: ERROR %s", symbol, r["error"])
            continue
        proposal: TradeProposal | None = r.get("proposal")
        decision: RiskDecision | None = r.get("decision")
        execution: ExecutionResult | None = r.get("execution")
        if execution:
            logger.info(
                "%s: EXECUTED %s %.4f @ %.2f (proposal=%s conf=%.2f)",
                symbol, execution.action, execution.quantity, execution.filled_price,
                proposal.action, proposal.confidence,
            )
        elif decision and not decision.approved:
            logger.info("%s: proposal=%s REJECTED (%s)", symbol, proposal.action, decision.reason)
        else:
            logger.info("%s: proposal=%s (no action)", symbol, proposal.action if proposal else "?")


async def _maybe_run_learning(orchestrator: Orchestrator, cfg: AppConfig) -> None:
    if not cfg.run_learning_after_each_cycle:
        return
    result = await orchestrator.run_learning_cycle()
    if result:
        logger.info("LearningActor: %s", result["message"])


async def run_once(config_path: str, bypass_market_hours: bool) -> None:
    if not bypass_market_hours and not is_market_open():
        logger.info("US market closed; skipping scan (use --bypass-market-hours to force)")
        return
    cfg = load_config(config_path)
    orchestrator = build_orchestrator(config_path)
    results = await orchestrator.run_scan_cycle()
    _summarize(results)
    await _maybe_run_learning(orchestrator, cfg)


async def run_loop(config_path: str, bypass_market_hours: bool) -> None:
    cfg = load_config(config_path)
    orchestrator = build_orchestrator(config_path)
    interval = cfg.scan_interval_minutes * 60
    while True:
        if bypass_market_hours or is_market_open():
            results = await orchestrator.run_scan_cycle()
            _summarize(results)
            await _maybe_run_learning(orchestrator, cfg)
        else:
            logger.info("Market closed; sleeping")
        await asyncio.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="Paper trading system with isolated actor agents")
    parser.add_argument("--config", default="config.yaml")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true", help="Run a single scan cycle and exit")
    mode.add_argument("--loop", action="store_true", help="Run continuously on the configured interval")
    parser.add_argument("--bypass-market-hours", action="store_true")
    args = parser.parse_args()

    if args.once:
        asyncio.run(run_once(args.config, args.bypass_market_hours))
    else:
        asyncio.run(run_loop(args.config, args.bypass_market_hours))


if __name__ == "__main__":
    main()
