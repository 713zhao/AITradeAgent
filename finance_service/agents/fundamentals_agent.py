"""FundamentalsAgent - Fetches and analyzes company fundamental metrics.

Uses OpenBB to retrieve financial statements, valuation ratios, and sector data.
Results are cached aggressively (24h) as fundamentals change slowly.
"""
import os
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass, asdict
import numpy as np

from finance_service.agents.agent_interface import Agent, AgentReport
from finance_service.core.event_bus import Event, Events, get_event_bus
from finance_service.core.yaml_config import YAMLConfigEngine

logger = logging.getLogger(__name__)


@dataclass
class FundamentalsSnapshot:
    """Container for fundamental metrics"""
    symbol: str
    timestamp: datetime
    # Valuation
    pe_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    ps_ratio: Optional[float] = None
    ev_ebitda: Optional[float] = None
    # profitability
    roe: Optional[float] = None  # Return on Equity
    roa: Optional[float] = None  # Return on Assets
    net_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    # Growth
    revenue_growth_yoy: Optional[float] = None
    eps_growth_yoy: Optional[float] = None
    # Balance sheet
    debt_to_equity: Optional[float] = None
    current_ratio: Optional[float] = None
    # Quality scores (0-1)
    value_score: float = 0.5  # composite: low PE/PB/PS = high score
    quality_score: float = 0.5  # high ROE, low debt = high score
    growth_score: float = 0.5  # high revenue/EPS growth = high score

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data


class FundamentalsAgent(Agent):
    """Fetches fundamental data for a symbol and computes derived scores.

    Trigger: Called per-symbol after DataAgent (in parallel with NewsAgent).
    Caching: 24h TTL in storage/cache/fundamentals_{symbol}.json

    Configuration:
        finance.data.fetch_fundamentals: true/false
        finance.data.fundamentals_cache_ttl: 86400
    """

    @property
    def agent_id(self) -> str:
        return "fundamentals_agent"

    @property
    def goal(self) -> str:
        return "Provide fundamental metrics and valuation scores for strategy enhancement."

    def __init__(self, config_engine: YAMLConfigEngine):
        self.config_engine = config_engine
        self.event_bus = get_event_bus()
        self.cache_ttl = config_engine.get("finance", "data/fundamentals_cache_ttl", default=86400)
        logger.info(f"FundamentalsAgent initialized (cache TTL={self.cache_ttl}s)")

    async def run(self, payload: Dict[str, Any]) -> Optional[AgentReport]:
        """
        Fetch fundamentals for a symbol.

        Args:
            payload: {
                "symbol": "AAPL"
            }

        Returns:
            AgentReport with FundamentalsSnapshot in payload['fundamentals']
        """
        symbol = payload.get("symbol")
        if not symbol:
            return AgentReport(
                agent_id=self.agent_id,
                status="error",
                message="Missing symbol in payload",
                payload={}
            )

        logger.info(f"FundamentalsAgent: fetching data for {symbol}")

        # Check cache
        cached = self._get_from_cache(symbol)
        if cached:
            logger.debug(f"Cache hit for {symbol} fundamentals")
            return AgentReport(
                agent_id=self.agent_id,
                status="success",
                message=f"Fundamentals (cached) for {symbol}",
                payload={"fundamentals": cached.to_dict()}
            )

        # Fetch from OpenBB
        try:
            snapshot = await self._fetch_fundamentals(symbol)
            if snapshot:
                self._save_to_cache(symbol, snapshot)
                return AgentReport(
                    agent_id=self.agent_id,
                    status="success",
                    message=f"Fundamentals fetched for {symbol}",
                    payload={"fundamentals": snapshot.to_dict()}
                )
            else:
                return AgentReport(
                    agent_id=self.agent_id,
                    status="error",
                    message=f"No fundamental data available for {symbol}",
                    payload={}
                )
        except Exception as e:
            logger.error(f"Fundamentals fetch failed for {symbol}: {e}")
            return AgentReport(
                agent_id=self.agent_id,
                status="error",
                message=f"Fundamentals error: {e}",
                payload={}
            )

    async def _fetch_fundamentals(self, symbol: str) -> Optional[FundamentalsSnapshot]:
        """Use OpenBB to fetch fundamental metrics."""
        try:
            from openbb import obb
            # Get company overview
            profile = obb.stocks.fa.overview(symbol=symbol).to_dict()
            # Get key ratios
            ratios = obb.stocks.fa.ratios(symbol=symbol, period='annual').iloc[0].to_dict()
            # Get income statement for growth
            income = obb.stocks.fa.income(symbol=symbol, period='annual').iloc[0].to_dict()

            # Extract metrics
            snapshot = FundamentalsSnapshot(
                symbol=symbol,
                timestamp=datetime.now(),
                pe_ratio=ratios.get('pe_ratio'),
                pb_ratio=ratios.get('pb_ratio'),
                ps_ratio=ratios.get('ps_ratio'),
                ev_ebitda=ratios.get('ev_ebitda'),
                roe=ratios.get('roe'),
                roa=ratios.get('roa'),
                net_margin=ratios.get('net_margin'),
                operating_margin=ratios.get('operating_margin'),
                revenue_growth_yoy=income.get('gross_profit')/100 if income.get('gross_profit') else None,  # placeholder
                eps_growth_yoy=ratios.get('eps_growth'),
                debt_to_equity=ratios.get('debt_to_equity'),
                current_ratio=ratios.get('current_ratio'),
            )
            # Compute composite scores (0-1)
            snapshot.value_score = self._compute_value_score(snapshot)
            snapshot.quality_score = self._compute_quality_score(snapshot)
            snapshot.growth_score = self._compute_growth_score(snapshot)

            return snapshot
        except Exception as e:
            logger.error(f"OpenBB fundamental fetch error for {symbol}: {e}")
            return None

    def _compute_value_score(self, f: FundamentalsSnapshot) -> float:
        """Composite value score: lower PE/PB/PS → higher score"""
        scores = []
        if f.pe_ratio and f.pe_ratio > 0:
            scores.append(min(1.0, 20 / f.pe_ratio))  # cap at 20
        if f.pb_ratio and f.pb_ratio > 0:
            scores.append(min(1.0, 3 / f.pb_ratio))
        if f.ps_ratio and f.ps_ratio > 0:
            scores.append(min(1.0, 5 / f.ps_ratio))
        return np.mean(scores) if scores else 0.5

    def _compute_quality_score(self, f: FundamentalsSnapshot) -> float:
        """Composite quality: high ROE, low debt"""
        scores = []
        if f.roe:
            scores.append(min(1.0, f.roe / 20.0))  # 20% = 1.0
        if f.current_ratio and f.current_ratio > 0:
            scores.append(min(1.0, f.current_ratio / 2.0))  # 2.0 = 1.0
        if f.debt_to_equity and f.debt_to_equity > 0:
            scores.append(1.0 - min(1.0, f.debt_to_equity / 100.0))  # less debt = better
        return np.mean(scores) if scores else 0.5

    def _compute_growth_score(self, f: FundamentalsSnapshot) -> float:
        """Growth score: revenue & EPS growth"""
        scores = []
        if f.revenue_growth_yoy:
            scores.append(min(1.0, f.revenue_growth_yoy / 0.30))  # 30% = 1.0
        if f.eps_growth_yoy:
            scores.append(min(1.0, f.eps_growth_yoy / 0.30))
        return np.mean(scores) if scores else 0.5

    def _cache_path(self, symbol: str) -> str:
        storage = os.getenv("STORAGE_DIR", "storage")
        return os.path.join(storage, "fundamentals_cache", f"{symbol}.json")

    def _get_from_cache(self, symbol: str) -> Optional[FundamentalsSnapshot]:
        import json, os
        path = self._cache_path(symbol)
        if not os.path.exists(path):
            return None
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            # Check age
            ts = datetime.fromisoformat(data['timestamp'])
            if (datetime.now() - ts).total_seconds() > self.cache_ttl:
                return None
            # Reconstruct
            return FundamentalsSnapshot(**data)
        except Exception as e:
            logger.warning(f"Fundamentals cache read failed for {symbol}: {e}")
            return None

    def _save_to_cache(self, symbol: str, snapshot: FundamentalsSnapshot):
        import json, os
        path = self._cache_path(symbol)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w') as f:
                json.dump(snapshot.to_dict(), f, indent=2)
        except Exception as e:
            logger.warning(f"Fundamentals cache write failed for {symbol}: {e}")
