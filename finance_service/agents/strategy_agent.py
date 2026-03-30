import logging
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, asdict
import pandas as pd

from finance_service.agents.agent_interface import Agent, AgentReport
from finance_service.core.event_bus import Event, Events, get_event_bus
from finance_service.core.models import TradeProposal
from finance_service.indicators.models import IndicatorsSnapshot, SignalType, IndicatorResult

logger = logging.getLogger(__name__)

class RuleType(Enum):
    """Type of trading rule"""
    ENTRY = "entry"
    EXIT = "exit"

@dataclass
class Rule:
    """Single trading rule"""
    name: str  # 'rsi_oversold', 'price_above_sma', etc.
    type: RuleType  # ENTRY or EXIT
    indicator: str  # 'rsi', 'macd', 'sma_20', etc.
    condition: str  # 'less_than', 'greater_than', 'crosses_above', etc.
    value: float  # threshold value
    enabled: bool = True
    compare_to_price: bool = False  # If True, compare current_price to indicator value instead of indicator value to threshold
    
    def __str__(self):
        return f"{self.name} ({self.type.value}): {self.indicator} {self.condition} {self.value}"

class RuleStrategy:
    """Evaluates entry/exit rules against indicators"""
    
    def __init__(self, rules_config: List[Dict]):
        """
        Initialize strategy with rules
        
        Args:
            rules_config: List of rule dicts from config
                Each dict should have: name, type, indicator, condition, value, enabled
        """
        self.rules = self._parse_rules(rules_config)
        self.entry_rules = [r for r in self.rules if r.type == RuleType.ENTRY]
        self.exit_rules = [r for r in self.rules if r.type == RuleType.EXIT]
        
        logger.info(f"RuleStrategy initialized: {len(self.entry_rules)} entry, {len(self.exit_rules)} exit rules")
    
    def _parse_rules(self, rules_config: List[Dict]) -> List[Rule]:
        """Parse rules from YAML config format"""
        rules = []
        for rule_cfg in rules_config:
            try:
                rule = Rule(
                    name=rule_cfg.get('name'),
                    type=RuleType(rule_cfg.get('type', 'entry')),
                    indicator=rule_cfg.get('indicator'),
                    condition=rule_cfg.get('condition'),
                    value=rule_cfg.get('value'),
                    enabled=rule_cfg.get('enabled', True),
                    compare_to_price=rule_cfg.get('compare_to_price', False)
                )
                rules.append(rule)
                logger.debug(f"Parsed rule: {rule}")
            except Exception as e:
                logger.error(f"Error parsing rule {rule_cfg}: {e}")
                raise
        return rules
    
    def evaluate_entry(self, indicators_snapshot: IndicatorsSnapshot) -> Tuple[bool, float, List[str]]:
        """
        Evaluate entry rules against indicators
        
        Args:
            indicators_snapshot: IndicatorsSnapshot with all indicators
        
        Returns:
            Tuple of:
                - should_buy (bool): True if entry conditions met
                - confidence (float): 0.0-1.0, ratio of rules triggered
                - triggered_rules (list): Names of rules that triggered
        """
        triggered = []
        
        for rule in self.entry_rules:
            if not rule.enabled:
                continue
            
            # Get indicator result
            ind = indicators_snapshot.indicators.get(rule.indicator)
            if not ind:
                logger.warning(f"Rule {rule.name}: indicator {rule.indicator} not found")
                continue
            
            # Determine value to compare based on rule's compare_to_price flag
            if getattr(rule, 'compare_to_price', False):
                # Compare current price to indicator value (e.g., price > sma)
                compare_value = indicators_snapshot.current_price
                threshold_value = ind.value
            else:
                compare_value = ind.value
                threshold_value = rule.value
            
            # Evaluate condition
            if self._check_condition(compare_value, rule.condition, threshold_value):
                triggered.append(rule.name)
        
        if not triggered:
            return False, 0.0, []
        
        # Calculate confidence as % of entry rules triggered
        enabled_entry_rules = [r for r in self.entry_rules if r.enabled]
        confidence = len(triggered) / len(enabled_entry_rules) if enabled_entry_rules else 0.0
        
        logger.info(f"Entry evaluation: {len(triggered)}/{len(enabled_entry_rules)} rules triggered (conf: {confidence:.2%})")
        
        return True, confidence, triggered
    
    def evaluate_exit(self, indicators_snapshot: IndicatorsSnapshot) -> Tuple[bool, List[str]]:
        """
        Evaluate exit rules against indicators
        
        Args:
            indicators_snapshot: IndicatorsSnapshot with all indicators
        
        Returns:
            Tuple of:
                - should_sell (bool): True if exit conditions met
                - triggered_rules (list): Names of rules that triggered
        """
        triggered = []
        
        for rule in self.exit_rules:
            if not rule.enabled:
                continue
            
            # Get indicator result
            ind = indicators_snapshot.indicators.get(rule.indicator)
            if not ind:
                logger.warning(f"Rule {rule.name}: indicator {rule.indicator} not found")
                continue
            
            # Evaluate condition
            if self._check_condition(ind.value, rule.condition, rule.value):
                triggered.append(rule.name)
        
        should_sell = len(triggered) > 0
        
        if should_sell:
            logger.info(f"Exit evaluation: {len(triggered)} rules triggered: {triggered}")
        
        return should_sell, triggered
    
    @staticmethod
    def _check_condition(value: float, condition: str, threshold: float) -> bool:
        """
        Check if condition is met
        
        Args:
            value: Indicator value
            condition: Condition type (less_than, greater_than, equals)
            threshold: Threshold value
        
        Returns:
            bool: True if condition met
        """
        if condition == 'less_than':
            return value < threshold
        elif condition == 'greater_than':
            return value > threshold
        elif condition == 'equals':
            return abs(value - threshold) < 0.001
        elif condition == 'less_than_or_equal':
            return value <= threshold
        elif condition == 'greater_than_or_equal':
            return value >= threshold
        else:
            logger.warning(f"Unknown condition: {condition}")
            return False


class StrategyAgent(Agent):
    """Strategy Agent - Generates trade proposals based on market analysis and news."""

    @property
    def agent_id(self) -> str:
        return "strategy_agent"

    @property
    def goal(self) -> str:
        return "Generate actionable trade proposals by analyzing market indicators and news sentiment."

    def __init__(self, config_engine, portfolio_agent=None):
        self.config_engine = config_engine
        self.event_bus = get_event_bus()
        # Load rules from YAML config using correct pattern
        rules_config = self._load_rules_from_config()
        self.rule_strategy = RuleStrategy(rules_config)
        # Load portfolio and risk parameters for position sizing
        self.initial_cash = self.config_engine.get("finance", "portfolio/initial_cash", default=100000.0)
        # Get active strategy's risk_budget_pct
        strategy_name = self.config_engine.get("finance", "strategy/type", default=None)
        self.risk_budget_pct = 1.5  # default
        if strategy_name:
            strategies = self.config_engine.get("finance", "strategies", default={})
            if isinstance(strategies, dict) and strategy_name in strategies:
                strat_cfg = strategies[strategy_name]
                self.risk_budget_pct = strat_cfg.get('risk_budget_pct', 1.5)
        # Inject portfolio_agent for position-awareness (FIX 2)
        self.portfolio_agent = portfolio_agent
        # Position cooling: track last entry per symbol to avoid stacking
        self.last_entry_time: Dict[str, datetime] = {}
        # Cooling period in hours (configurable)
        self.position_cooling_hours = self.config_engine.get("finance", "strategy/position_cooling_hours", default=24)
        logger.info(f"StrategyAgent: portfolio_value=${self.initial_cash:,.2f}, risk_budget_pct={self.risk_budget_pct}%, position_cooling_hours={self.position_cooling_hours}")
        logger.info(f"StrategyAgent initialized with {len(rules_config)} rules")

    def _load_rules_from_config(self) -> List[Dict]:
        """Load trading rules from YAML configuration."""
        # New approach: select a strategy from the strategies dict by name
        strategy_name = self.config_engine.get("finance", "strategy/type", default=None)
        if strategy_name:
            strategies = self.config_engine.get("finance", "strategies", default={})
            if isinstance(strategies, dict) and strategy_name in strategies:
                strat_cfg = strategies[strategy_name]
                entry_rules = strat_cfg.get('entry_rules', [])
                exit_rules = strat_cfg.get('exit_rules', [])
                all_rules = entry_rules + exit_rules
                logger.info(f"Loaded strategy '{strategy_name}' with {len(entry_rules)} entry and {len(exit_rules)} exit rules")
                return all_rules
            else:
                available = ", ".join(strategies.keys()) if isinstance(strategies, dict) else "none"
                logger.error(f"Strategy '{strategy_name}' not found in strategies. Available: {available}")
        
        # Fallback to legacy format (boolean flags)
        logger.warning("Falling back to legacy strategy config format")
        rules = []
        rules_enabled = self.config_engine.get("finance", "strategy/rules", default={})
        if isinstance(rules_enabled, dict):
            rule_map = {
                'rsi_entry_oversold': {
                    'name': 'rsi_oversold_entry',
                    'type': 'entry',
                    'indicator': 'rsi',
                    'condition': 'less_than',
                    'value': self.config_engine.get("finance", "strategy/rules/rsi_entry_oversold_threshold", default=35)
                },
                'macd_crossover': {
                    'name': 'macd_bullish_entry',
                    'type': 'entry',
                    'indicator': 'macd',
                    'condition': 'greater_than',
                    'value': 0
                },
                'price_above_sma': {
                    'name': 'price_above_sma20_entry',
                    'type': 'entry',
                    'indicator': 'sma20',
                    'condition': 'greater_than',
                    'value': 0,
                    'compare_to_price': True
                },
                'rsi_exit_overbought': {
                    'name': 'rsi_overbought_exit',
                    'type': 'exit',
                    'indicator': 'rsi',
                    'condition': 'greater_than',
                    'value': self.config_engine.get("finance", "strategy/rules/rsi_exit_overbought_threshold", default=70)
                },
                'macd_signal_exit': {
                    'name': 'macd_signal_cross_exit',
                    'type': 'exit',
                    'indicator': 'macd_histogram',
                    'condition': 'less_than',
                    'value': 0
                }
            }
            for flag_name, rule_def in rule_map.items():
                if rules_enabled.get(flag_name, False):
                    rule = rule_def.copy()
                    rule['enabled'] = True
                    rules.append(rule)
                    logger.info(f"Enabled rule: {rule['name']} ({rule['type']})")
        else:
            if isinstance(rules_enabled, list):
                rules = rules_enabled
            else:
                logger.warning(f"Unexpected rules config type: {type(rules_enabled)}")
        
        # Always-on exit rules placeholder (disabled by default)
        rules.append({
            'name': 'always_exit_on_stop',
            'type': 'exit',
            'indicator': 'always',
            'condition': 'equals',
            'value': 0,
            'enabled': False
        })
        
        logger.info(f"Loaded {len(rules)} rules from config")
        return rules

    async def run(self, analysis_payload: Dict[str, Any], symbol: str = None) -> AgentReport:
        """
        Generate trade proposals based on market analysis and news.
        
        Args:
            indicators_report: AgentReport with indicators_snapshot
            news_report: AgentReport with news sentiment
        
        Returns:
            AgentReport with proposals list in payload
        """
        try:
            # Get indicator snapshot from analysis report
            indicators_snapshot = analysis_payload.get("indicators_snapshot")
            if not indicators_snapshot:
                return AgentReport(
                    agent_id=self.agent_id,
                    status="error",
                    message="No indicators_snapshot in analysis_report"
                )
            
            # Evaluate entry/exit rules
            should_buy, confidence, entry_rules = self.rule_strategy.evaluate_entry(indicators_snapshot)
            should_sell, exit_rules = self.rule_strategy.evaluate_exit(indicators_snapshot)
            
            # Build trade proposals if entry signal
            proposals = []
            if should_buy:
                symbol = indicators_snapshot.symbol
                # Use close price as target for market orders
                current_price = indicators_snapshot.current_price
                target_price = current_price
                
                # --- FIX 2 & 5: Position cooling and position-awareness ---
                now = datetime.utcnow()
                # Cooling: skip if we traded this symbol recently
                last_entry = self.last_entry_time.get(symbol)
                if last_entry:
                    cooling_hours = self.position_cooling_hours
                    if (now - last_entry).total_seconds() < cooling_hours * 3600:
                        logger.info(f"Position cooling: skipping {symbol} - last entry was {(now-last_entry).total_seconds()/3600:.1f}h ago (minimum {cooling_hours}h)")
                        return AgentReport(
                            agent_id=self.agent_id,
                            status="success",
                            message=f"Position cooling active for {symbol}",
                            payload={"proposals": []}
                        )
                
                # Check existing position size if portfolio_agent available
                existing_qty = 0
                max_position_size_pct = 10.0  # default from risk policy
                portfolio_equity = self.initial_cash
                if self.portfolio_agent:
                    try:
                        from finance_service.core.event_bus import Events
                        portfolio_report = await self.portfolio_agent.run(event_type=Events.GET_PORTFOLIO_STATE, payload={})
                        if portfolio_report.status == "success":
                            portfolio_data = portfolio_report.payload
                            # find existing position
                            for pos in portfolio_data.get("positions", []):
                                if pos["symbol"] == symbol:
                                    existing_qty = pos["quantity"]
                                    break
                            portfolio_equity = portfolio_data["equity_metrics"]["total_equity"]
                            # get max position size from risk config (fallback)
                            max_position_size_pct = self.config_engine.get("finance", "risk/max_position_size_pct", default=10.0)
                    except Exception as e:
                        logger.warning(f"Failed to query portfolio_agent for position cooling: {e}")
                
                # Calculate stop loss based on ATR (2x ATR default)
                atr_indicator = indicators_snapshot.indicators.get('atr')
                if atr_indicator:
                    atr_value = atr_indicator.value
                else:
                    # Fallback: 2% of price if ATR not available
                    atr_value = current_price * 0.02
                
                stop_loss_price = round(current_price - (atr_value * 2), 2)
                # Ensure stop is below current price
                if stop_loss_price >= current_price:
                    stop_loss_price = round(current_price * 0.95, 2)  # 5% below as fallback
                
                # Position sizing: risk-based, respecting existing exposure
                risk_per_share = current_price - stop_loss_price
                if risk_per_share <= 0:
                    logger.warning(f"Invalid risk_per_share for {symbol}: {risk_per_share}. Using default 1 share.")
                    quantity = 1
                else:
                    # Maximum loss amount we're willing to take for this trade
                    risk_budget_usd = portfolio_equity * (self.risk_budget_pct / 100.0)
                    desired_quantity = int(risk_budget_usd / risk_per_share)
                    desired_quantity = max(1, desired_quantity)
                    
                    # --- FIX 2: Adjust quantity to respect max position size ---
                    # Compute total position after trade
                    total_qty = existing_qty + desired_quantity
                    # Max allowed qty based on % of portfolio
                    max_allowed_value = portfolio_equity * (max_position_size_pct / 100.0)
                    max_allowed_qty = int(max_allowed_value / current_price)
                    if total_qty > max_allowed_qty:
                        quantity = max(0, max_allowed_qty - existing_qty)
                        if quantity == 0:
                            logger.info(f"Position size limit: existing {existing_qty} shares, max allowed {max_allowed_qty}. Skipping entry.")
                            return AgentReport(
                                agent_id=self.agent_id,
                                status="success",
                                message=f"Position size limit reached for {symbol}",
                                payload={"proposals": []}
                            )
                        else:
                            logger.info(f"Reduced quantity from {desired_quantity} to {quantity} due to position size limit (existing: {existing_qty})")
                    else:
                        quantity = desired_quantity
                
                proposal = TradeProposal(
                    symbol=symbol,
                    action="BUY",
                    confidence=confidence,
                    target_price=target_price,
                    stop_loss_price=stop_loss_price,
                    rationale=[f"Entry rules triggered: {entry_rules}"]
                )
                # Attach quantity separately (not part of TradeProposal model but needed for execution)
                # We'll include it in the dict representation
                proposal_dict = asdict(proposal)
                proposal_dict['quantity'] = quantity
                proposals.append(proposal_dict)
                # Record entry time for cooling
                self.last_entry_time[symbol] = now
            
            # Note: Exits are handled by PortfolioAgent when rules trigger; strategy only generates BUY proposals
            
            if proposals:
                logger.info(f"Strategy generated {len(proposals)} trade proposal(s)")
                return AgentReport(
                    agent_id=self.agent_id,
                    status="success",
                    message=f"Generated {len(proposals)} trade proposals",
                    payload={"proposals": proposals}
                )
            else:
                # No proposals generated - this is normal, not an error
                return AgentReport(
                    agent_id=self.agent_id,
                    status="success",
                    message="No trade proposals generated",
                    payload={"proposals": []}
                )
                
        except Exception as e:
            logger.error(f"Error in StrategyAgent.run: {e}", exc_info=True)
            return AgentReport(
                agent_id=self.agent_id,
                status="error",
                message=f"StrategyAgent error: {e}"
            )

    def _evaluate_strategies(self, indicators_report: AgentReport, news_report: AgentReport) -> list[TradeProposal]:
        """
        Internal method to evaluate various trading strategies.
        """
        proposals: List[TradeProposal] = []

        if indicators_report and indicators_report.status == "success":
            payload = indicators_report.payload.copy()  # Don't mutate original
            # Remove computed 'signals' field if present (IndicatorsSnapshot doesn't accept it)
            payload.pop('signals', None)

            # Reconstruct IndicatorResult objects from dicts
            indicators_dict = payload.get('indicators', {})
            reconstructed_indicators = {}
            for name, ind_data in indicators_dict.items():
                if isinstance(ind_data, dict):
                    # Convert dict back to IndicatorResult
                    # Convert signal string to SignalType enum
                    signal_str = ind_data.get('signal', 'HOLD')
                    try:
                        signal_enum = SignalType[signal_str] if signal_str in SignalType.__members__ else SignalType(signal_str)
                    except:
                        signal_enum = SignalType.HOLD
                    timestamp = pd.Timestamp(ind_data.get('timestamp')) if ind_data.get('timestamp') else pd.Timestamp.now()
                    reconstructed_indicators[name] = IndicatorResult(
                        name=ind_data.get('name', name),
                        value=float(ind_data.get('value', 0)),
                        signal=signal_enum,
                        timestamp=timestamp,
                        metadata=ind_data.get('metadata', {})
                    )
                else:
                    # Already an IndicatorResult object
                    reconstructed_indicators[name] = ind_data
            payload['indicators'] = reconstructed_indicators

            indicators_snapshot = IndicatorsSnapshot(**payload)
            symbol = indicators_snapshot.symbol

            should_buy, buy_confidence, entry_rules = self.rule_strategy.evaluate_entry(indicators_snapshot)
            should_sell, exit_rules = self.rule_strategy.evaluate_exit(indicators_snapshot)

            # Simple decision logic for now, can be expanded
            if should_buy and not should_sell:
                # Placeholder for calculating target and stop prices using ATR or other methods
                current_price = indicators_snapshot.current_price
                # Assuming ATR is available in indicators_snapshot, if not, use a default/fallback
                atr_value = indicators_snapshot.indicators.get('atr', None)
                atr_value = atr_value.value if atr_value else (current_price * 0.02) # Default 2% of price if ATR not found

                target_price = round(current_price * 1.05, 2) # Example: 5% above
                stop_loss_price = round(current_price - (atr_value * 2), 2) # Example: 2x ATR below

                proposals.append(asdict(TradeProposal(
                    symbol=symbol,
                    action="BUY",
                    confidence=buy_confidence,
                    target_price=target_price,
                    stop_loss_price=stop_loss_price,
                    rationale=entry_rules
                )))
            elif should_sell:
                # For now, if sell signals, we propose to sell existing positions
                # In a real scenario, this would check existing positions and propose selling relevant quantity
                current_price = indicators_snapshot.current_price
                atr_value = indicators_snapshot.indicators.get('atr', None)
                atr_value = atr_value.value if atr_value else (current_price * 0.02)

                target_price = round(current_price * 0.95, 2)
                stop_loss_price = round(current_price + (atr_value * 2), 2)

                proposals.append(asdict(TradeProposal(
                    symbol=symbol,
                    action="SELL",
                    confidence=0.7, # Placeholder confidence for selling
                    target_price=target_price,
                    stop_loss_price=stop_loss_price,
                    rationale=exit_rules
                )))
        
        logger.debug(f"Generated {len(proposals)} proposals.")
        return proposals

    def __repr__(self) -> str:
        return f"<StrategyAgent(id='{self.agent_id}')>"
