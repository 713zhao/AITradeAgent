"""
RankingAgent — Intelligent Symbol Ranking with Explainability

Purpose:
    Provides rich, explainable ranking of discovered symbols using multi-factor scoring.
    Independent from MarketScannerAgent: can re-rank at any time.
    Produces detailed scoring breakdown for transparency and learning.

Trigger: MARKET_SCANNED event (per discovery batch)

Output Event: RANKING_COMPLETE
    - ranked_symbols: sorted by composite score
    - ranking_factors: breakdown of each factor's contribution
    - explanations: human-readable rationale for each symbol
"""

import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from datetime import datetime

from finance_service.agents.agent_interface import Agent, AgentReport
from finance_service.core.event_bus import get_event_bus
from finance_service.core.yaml_config import YAMLConfigEngine

logger = logging.getLogger(__name__)


@dataclass
class RankingFactor:
    """Single factor in composite score."""
    name: str
    weight: float
    raw_value: float
    normalized_score: float
    contribution: float


class RankingAgent(Agent):
    """
    Multi-factor symbol ranking with explainability.
    
    Scoring: liquidity (20%) + momentum (25%) + value (20%) + growth (20%) + quality (15%)
    Each factor normalized 0-1 and weighted for composite score.
    """

    def __init__(self, config_engine: YAMLConfigEngine):
        self.config = config_engine
        self.event_bus = get_event_bus()
        self.weights = {
            "liquidity": 0.20,
            "momentum": 0.25,
            "value": 0.20,
            "growth": 0.20,
            "quality": 0.15,
        }
        self.thresholds = {
            "min_volume_usd": 1_000_000,
            "max_volume_usd": 100_000_000,
            "min_pe": 5,
            "max_pe": 40,
            "min_roe": 0.05,
            "max_roe": 0.30,
        }
        logger.info("RankingAgent initialized")

    @property
    def agent_id(self) -> str:
        return "ranking_agent"

    @property
    def goal(self) -> str:
        return "Provide explainable, multi-factor ranking of symbols"

    async def run(self, symbols_with_data: Dict[str, Any]) -> Dict[str, Any]:
        """Re-rank symbols with full scoring breakdown."""
        try:
            ranked_symbols = []
            
            for symbol, data in symbols_with_data.items():
                theme = data.get("theme", "unknown")
                fundamentals = data.get("fundamentals", {})
                indicators = data.get("indicators", {})
                
                # Score factors
                factors = self._score_factors(symbol, fundamentals, indicators)
                composite_score = sum(f.contribution for f in factors)
                confidence = self._compute_confidence(fundamentals, indicators)
                explanation = self._generate_explanation(symbol, factors)
                
                ranked_symbols.append({
                    "symbol": symbol,
                    "theme": theme,
                    "composite_score": composite_score,
                    "confidence": confidence,
                    "factors": [{
                        "name": f.name,
                        "weight": f.weight,
                        "raw_value": f.raw_value,
                        "normalized_score": f.normalized_score,
                        "contribution": f.contribution,
                    } for f in factors],
                    "explanation": explanation,
                })
            
            # Sort and rank
            ranked_symbols.sort(
                key=lambda x: (-x["composite_score"], x["symbol"])
            )
            for rank, rs in enumerate(ranked_symbols, 1):
                rs["rank"] = rank
            
            logger.info(f"RankingAgent: ranked {len(ranked_symbols)} symbols")
            
            return {
                "agent_id": self.agent_id,
                "status": "success",
                "payload": {
                    "ranked_symbols": ranked_symbols,
                    "ranking_timestamp": datetime.utcnow().isoformat() + "Z",
                    "total_symbols": len(ranked_symbols),
                },
            }
        except Exception as e:
            logger.error(f"RankingAgent.run() failed: {e}", exc_info=True)
            return {
                "agent_id": self.agent_id,
                "status": "error",
                "payload": {"error": str(e)},
            }

    def _score_factors(self, symbol: str, fundamentals: Dict, indicators: Dict) -> List[RankingFactor]:
        """Compute 5-factor scores."""
        factors = []
        
        # Liquidity
        volume_usd = fundamentals.get("volume_usd", 0)
        liquidity_score = min(1.0, max(0.0, (volume_usd - self.thresholds["min_volume_usd"]) / (self.thresholds["max_volume_usd"] - self.thresholds["min_volume_usd"])))
        factors.append(RankingFactor("liquidity", self.weights["liquidity"], volume_usd, liquidity_score, self.weights["liquidity"] * liquidity_score))
        
        # Momentum
        rsi = indicators.get("rsi", 50)
        rsi_score = 0.5 if 30 <= rsi <= 70 else (0.75 if 20 <= rsi <= 80 else 0.5)
        factors.append(RankingFactor("momentum", self.weights["momentum"], rsi, rsi_score, self.weights["momentum"] * rsi_score))
        
        # Value
        pe = fundamentals.get("pe_ratio", 20)
        value_score = max(0.0, 1.0 - (pe - self.thresholds["min_pe"]) / (self.thresholds["max_pe"] - self.thresholds["min_pe"]) * 0.8) if pe > 0 else 0.5
        factors.append(RankingFactor("value", self.weights["value"], pe, value_score, self.weights["value"] * value_score))
        
        # Growth
        growth = fundamentals.get("eps_growth", 0.10)
        growth_score = min(1.0, max(0.0, growth / 0.20))
        factors.append(RankingFactor("growth", self.weights["growth"], growth, growth_score, self.weights["growth"] * growth_score))
        
        # Quality
        roe = fundamentals.get("roe", 0.15)
        quality_score = min(1.0, max(0.0, (roe - self.thresholds["min_roe"]) / (self.thresholds["max_roe"] - self.thresholds["min_roe"])))
        factors.append(RankingFactor("quality", self.weights["quality"], roe, quality_score, self.weights["quality"] * quality_score))
        
        return factors

    def _compute_confidence(self, fundamentals: Dict, indicators: Dict) -> float:
        """Confidence based on data completeness."""
        required = ["pe_ratio", "roe", "volume_usd"]
        available = sum(1 for f in required if f in fundamentals and fundamentals[f])
        return available / len(required)

    def _generate_explanation(self, symbol: str, factors: List[RankingFactor]) -> str:
        """Human-readable explanation."""
        top_factors = sorted(factors, key=lambda f: f.contribution, reverse=True)[:3]
        reasons = [f"{f.name.title()} ({f.normalized_score:.2f})" for f in top_factors]
        return f"{symbol}: {', '.join(reasons)}"
