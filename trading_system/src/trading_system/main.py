"""CLI entrypoint. Usage:

  python -m trading_system.main --config config.yaml --once
  python -m trading_system.main --config config.yaml --loop
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import json

from trading_system.agents.analysis_agent import AnalysisAgent
from trading_system.agents.data_agent import DataAgent, YFinanceProvider
from trading_system.agents.execution_agent import ExecutionAgent
from trading_system.agents.learning_agent import LearningAgent
from trading_system.agents.portfolio_agent import PortfolioAgent, PortfolioStore
from trading_system.agents.risk_agent import RiskAgent, RiskPolicy
from trading_system.agents.scanner_agent import ScannerAgent
from trading_system.agents.strategy_agent import StrategyAgent
from trading_system.broker.paper_broker import PaperBroker
from trading_system.config.loader import load_config
from trading_system.core.market_hours import is_us_market_open
from trading_system.core.models import ExecutionResult, RiskDecision, TradeProposal
from trading_system.llm.client import NullLLMClient, OpenAICompatibleClient
from trading_system.memory.store import MemoryStore
from trading_system.orchestrator import Orchestrator

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("trading_system.main")


def build_orchestrator(config_path: str) -> Orchestrator:
    cfg = load_config(config_path)

    llm_client = None
    if cfg.llm.enabled:
        api_key = os.environ.get(cfg.llm.api_key_env)
        if not api_key:
            logger.warning("LLM enabled but %s not set; falling back to rule strategy", cfg.llm.api_key_env)
        else:
            llm_client = OpenAICompatibleClient(api_key=api_key, model=cfg.llm.model, base_url=cfg.llm.base_url)

    memory = MemoryStore(cfg.memory_db_path)

    scanner = ScannerAgent(cfg.universe, limit=cfg.scan_limit)
    data_agent = DataAgent(YFinanceProvider())
    analysis_agent = AnalysisAgent()
    strategy_agent = StrategyAgent(llm_client=llm_client, memory=memory)
    risk_agent = RiskAgent(RiskPolicy(**cfg.risk.model_dump()), memory=memory)
    broker = PaperBroker(**cfg.broker.model_dump())
    execution_agent = ExecutionAgent(broker)
    store = PortfolioStore(cfg.db_path, starting_cash=cfg.starting_cash)
    portfolio_agent = PortfolioAgent(store)
    learning_agent = LearningAgent(memory=memory, llm_client=llm_client)

    return Orchestrator(
        scanner=scanner, data=data_agent, analysis=analysis_agent, strategy=strategy_agent,
        risk=risk_agent, execution=execution_agent, portfolio=portfolio_agent,
        lookback_days=cfg.lookback_days, memory=memory, learning=learning_agent,
    )


def _summarize(results: list[dict]) -> None:
    for r in results:
        symbol = r["symbol"]
        if "error" in r:
            logger.info("%s: ERROR %s", symbol, r["error"])
            continue
        proposal: TradeProposal = r.get("proposal")
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


async def _maybe_run_learning(orchestrator: Orchestrator, cfg) -> None:
    if not cfg.run_learning_after_each_cycle:
        return
    result = await orchestrator.run_learning_cycle()
    if result and result["status"] == "success":
        logger.info("LearningAgent: %s", result["payload"].get("lesson"))
    elif result:
        logger.info("LearningAgent: %s", result["message"])


async def run_once(config_path: str, bypass_market_hours: bool) -> None:
    if not bypass_market_hours and not is_us_market_open():
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
        if bypass_market_hours or is_us_market_open():
            results = await orchestrator.run_scan_cycle()
            _summarize(results)
            await _maybe_run_learning(orchestrator, cfg)
        else:
            logger.info("Market closed; sleeping")
        await asyncio.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="Multi-agent paper trading system")
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
