"""OptionsStrategyAgent - Generates options-based trade strategies.

Strategies:
- Covered Call: Sell OTM call against long stock position
- Cash-Secured Put: Sell OTM put to acquire stock at discount
- Directional: Buy calls/puts based on high-conviction signals

Trigger: Called when StrategyAgent generates a BUY/SELL proposal with existing position (for covered call) or high confidence (for CSP/directional).
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass, asdict

from finance_service.agents.agent_interface import Agent, AgentReport
from finance_service.core.event_bus import Event, Events, get_event_bus
from finance_service.core.yaml_config import YAMLConfigEngine
from finance_service.agents.options_data_agent import OptionsChain

logger = logging.getLogger(__name__)


@dataclass
class OptionsProposal:
    """Options trade proposal"""
    symbol: str
    option_type: str  # 'CALL' or 'PUT'
    expiration: str
    strike: float
    quantity: int  # number of contracts (100 shares each)
    action: str  # 'SELL' for covered call/CSP, 'BUY' for directional
    premium: float  # estimated premium (bid/ask)
    max_loss: float  # max potential loss (calculated)
    delta: Optional[float] = None
    iv: Optional[float] = None
    rationale: List[str] = None

    def __post_init__(self):
        if self.rationale is None:
            self.rationale = []

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class OptionsStrategyAgent(Agent):
    """Generates options-enhanced trading strategies.

    Configuration (config/config.yaml):
        finance.options.enabled: true
        finance.options.strategies: ['covered_call', 'csp', 'directional']
        finance.options.directional_confidence_threshold: 0.85
    """

    @property
    def agent_id(self) -> str:
        return "options_strategy_agent"

    @property
    def goal(self) -> str:
        return "Generate options-based trade strategies to enhance returns and manage risk."

    def __init__(self, config_engine: YAMLConfigEngine):
        self.config_engine = config_engine
        self.enabled = config_engine.get("finance", "options/enabled", default=False)
        self.allowed_strategies = config_engine.get("finance", "options/strategies", default=['covered_call'])
        self.directional_threshold = config_engine.get("finance", "options/directional_confidence_threshold", 0.85)
        logger.info(f"OptionsStrategyAgent initialized (enabled={self.enabled}, strategies={self.allowed_strategies})")

    async def run(self, payload: Dict[str, Any]) -> Optional[AgentReport]:
        """
        Generate options proposals based on a base signal and available options data.

        Args:
            payload: {
                "base_proposal": TradeProposal dict (from StrategyAgent),
                "options_chain": OptionsChain dict (from OptionsDataAgent),
                "portfolio_position": Optional[Position] (if holding underlying)
            }

        Returns:
            AgentReport with 'options_proposals' list (may be empty if no suitable options)
        """
        if not self.enabled:
            return AgentReport(self.agent_id, "success", "Options strategies disabled", {"options_proposals": []})

        base_proposal = payload.get("base_proposal")
        options_chain_dict = payload.get("options_chain")
        portfolio_position = payload.get("portfolio_position")  # Existing position dict

        if not base_proposal or not options_chain_dict:
            return AgentReport(self.agent_id, "success", "Missing options data or base proposal", {"options_proposals": []})

        symbol = base_proposal['symbol']
        logger.info(f"OptionsStrategyAgent evaluating strategies for {symbol}")

        proposals = []

        # Convert options chain dict back to object
        chain = OptionsChain(**options_chain_dict)

        # Strategy 1: Covered Call (if we own the stock and want to generate income)
        if 'covered_call' in self.allowed_strategies and portfolio_position:
            cc_proposal = self._evaluate_covered_call(portfolio_position, chain)
            if cc_proposal:
                proposals.append(cc_proposal.to_dict())

        # Strategy 2: Cash-Secured Put (if we want to acquire stock at discount)
        if 'csp' in self.allowed_strategies and base_proposal['action'] == 'BUY':
            # We're already planning to buy; consider CSP instead if attractive
            csp_proposal = self._evaluate_cash_secured_put(symbol, chain, base_proposal)
            if csp_proposal:
                proposals.append(csp_proposal.to_dict())

        # Strategy 3: Directional options (high confidence signal)
        if 'directional' in self.allowed_strategies and base_proposal['action'] == 'BUY' and base_proposal['confidence'] >= self.directional_threshold:
            dir_proposal = self._evaluate_directional_call(symbol, chain, base_proposal)
            if dir_proposal:
                proposals.append(dir_proposal.to_dict())

        logger.info(f"Generated {len(proposals)} options proposals for {symbol}")
        return AgentReport(
            self.agent_id,
            "success" if proposals else "success",
            f"Options strategies evaluated for {symbol}",
            {"options_proposals": proposals}
        )

    def _evaluate_covered_call(self, position: Dict, chain: OptionsChain) -> Optional[OptionsProposal]:
        """Evaluate selling a covered call against existing long stock."""
        # We need at least 100 shares per contract
        shares_owned = position.get('quantity', 0)
        if shares_owned < 100:
            return None

        contracts_available = shares_owned // 100
        current_price = chain.underlying_price

        # Find an OTM call with ~30-45 DTE, reasonable IV (top 25% of chain)
        target_dte = 30  # days
        expirations = [exp for exp in chain.expirations if self._dte(exp) >= target_dte]
        if not expirations:
            return None

        # Simple: pick first expiry for now (should sort by DTE)
        exp = expirations[0]
        strikes = chain.chains[exp]
        # Filter for OTM calls (strike > current_price)
        otm_calls = [c for c in strikes if c['option_type'] == 'CALL' and c['strike'] > current_price]
        if not otm_calls:
            return None

        # Choose strike with highest open interest (liquidity) and reasonable IV (e.g., top 50% of available)
        otm_calls.sort(key=lambda c: c['open_interest'], reverse=True)
        selected = otm_calls[0]  # could add more filtering

        # Premium: use bid (we sell at bid)
        premium = selected['bid'] * 100 * contracts_available  # total premium
        # Max loss: if stock goes above strike, we lose upside beyond strike minus premium
        max_loss = 0  # For covered call, max loss equals stock position loss (not increased by short call)
        # Actually, covered call has limited upside but not additional downside risk relative to long stock

        return OptionsProposal(
            symbol=chain.symbol,
            option_type='CALL',
            expiration=exp,
            strike=selected['strike'],
            quantity=contracts_available,
            action='SELL',
            premium=premium,
            max_loss=max_loss,
            delta=selected.get('delta'),
            iv=selected['iv'],
            rationale=[f"Covered call: sell {contracts_available} contracts OTM {exp} {selected['strike']}C, premium ${premium:.2f}"]
        )

    def _evaluate_cash_secured_put(self, symbol: str, chain: OptionsChain, base_proposal: Dict) -> Optional[OptionsProposal]:
        """Evaluate selling a cash-secured put to acquire stock at a discount."""
        # We need cash to secure: strike * 100 * quantity
        # Use confidence from base proposal to pick strike (higher confidence = further OTM)
        current_price = chain.underlying_price
        target_dte = 30
        expirations = [exp for exp in chain.expirations if self._dte(exp) >= target_dte]
        if not expirations:
            return None
        exp = expirations[0]

        strikes = chain.chains[exp]
        otm_puts = [c for c in strikes if c['option_type'] == 'PUT' and c['strike'] < current_price]
        if not otm_puts:
            return None

        # Sort by open interest, pick strike slightly OTM (5-10% below)
        otm_puts.sort(key=lambda c: c['open_interest'], reverse=True)
        # Could also choose based on confidence: higher confidence → further OTM (lower premium but better entry)
        selected = otm_puts[0]

        # Assume 1 contract for simplicity (should scale with cash)
        contracts = 1
        premium = selected['bid'] * 100 * contracts
        cash_required = selected['strike'] * 100 * contracts
        max_loss = cash_required - premium  # if stock goes to 0

        return OptionsProposal(
            symbol=chain.symbol,
            option_type='PUT',
            expiration=exp,
            strike=selected['strike'],
            quantity=contracts,
            action='SELL',
            premium=premium,
            max_loss=max_loss,
            delta=selected.get('delta'),
            iv=selected['iv'],
            rationale=[f"CSP: sell {contracts} {exp} {selected['strike']}P, premium ${premium:.2f}, cash required ${cash_required:.2f}"]
        )

    def _evaluate_directional_call(self, symbol: str, chain: OptionsChain, base_proposal: Dict) -> Optional[OptionsProposal]:
        """Evaluate buying a call option as a leveraged long position."""
        # Dump: buy an OTM call with 30-60 DTE, delta ~0.5-0.6
        current_price = chain.underlying_price
        target_dte = 60
        expirations = [exp for exp in chain.expirations if self._dte(exp) >= target_dte]
        if not expirations:
            return None
        exp = expirations[0]

        strikes = chain.chains[exp]
        otm_calls = [c for c in strikes if c['option_type'] == 'CALL' and c['strike'] > current_price]
        if not otm_calls:
            return None

        # Find call with delta around 0.5-0.6 (moderate exposure)
        suitable = [c for c in otm_calls if 0.4 <= abs(c.get('delta', 0) or 0) <= 0.7]
        if not suitable:
            suitable = otm_calls
        suitable.sort(key=lambda c: abs(c.get('delta', 0) - 0.55))  # closest to 0.55 delta
        selected = suitable[0]

        # Position size: use premium equivalent to (risk_budget % of portfolio) or limit
        # For now, 1 contract
        contracts = 1
        premium = selected['ask'] * 100 * contracts  # buy at ask
        max_loss = premium  # full premium loss if OTM

        return OptionsProposal(
            symbol=chain.symbol,
            option_type='CALL',
            expiration=exp,
            strike=selected['strike'],
            quantity=contracts,
            action='BUY',
            premium=premium,
            max_loss=max_loss,
            delta=selected.get('delta'),
            iv=selected['iv'],
            rationale=[f"Directional call: buy {contracts} {exp} {selected['strike']}C, premium ${premium:.2f} (delta {selected.get('delta'):.2f})"]
        )

    def _dte(self, expiration: str) -> int:
        """Calculate days to expiration"""
        try:
            exp_date = datetime.strptime(expiration, '%Y-%m-%d').date()
            return (exp_date - datetime.now().date()).days
        except Exception:
            return 0
