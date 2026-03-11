import logging
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from enum import Enum
from dataclasses import dataclass

from finance_service.agents.agent_interface import Agent, AgentReport
from finance_service.core.events import Event, Events, get_event_bus
from finance_service.core.models import TradeProposal
from finance_service.indicators.models import IndicatorsSnapshot, SignalType

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
                    enabled=rule_cfg.get('enabled', True)
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
            
            # Evaluate condition
            if self._check_condition(ind.value, rule.condition, rule.value):
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

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.event_bus = get_event_bus()
        self.rule_strategy = RuleStrategy(config.get("rules", [])) # Initialize RuleStrategy
        logger.info(f"StrategyAgent initialized with config: {self.config}")

    async def run(self, indicators_report: AgentReport, news_report: AgentReport) -> Optional[AgentReport]:
        """
        Generates trade proposals based on indicators and news.
        """
        logger.info("StrategyAgent run: Generating trade proposals.")
        
        try:
            trade_proposals = self._evaluate_strategies(indicators_report, news_report)

            if trade_proposals:
                message = f"{len(trade_proposals)} trade proposals generated."
                payload = {"proposals": [p.model_dump() for p in trade_proposals]}
                
                self.event_bus.publish(Event(
                    event_type=Events.TRADE_PROPOSAL_GENERATED,
                    data=payload
                ))
            else:
                message = "No trade proposals generated."
                payload = {"proposals": []}

            return AgentReport(
                agent_id=self.agent_id,
                status="success",
                message=message,
                payload=payload
            )
        except Exception as e:
            logger.error(f"Error in StrategyAgent run: {e}")
            return AgentReport(
                agent_id=self.agent_id,
                status="error",
                message=f"Error generating trade proposals: {e}"
            )

    def _evaluate_strategies(self, indicators_report: AgentReport, news_report: AgentReport) -> list[TradeProposal]:
        """
        Internal method to evaluate various trading strategies.
        """
        proposals: List[TradeProposal] = []

        if indicators_report and indicators_report.status == "success":
            indicators_snapshot = IndicatorsSnapshot(**indicators_report.payload)
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

                proposals.append(TradeProposal(
                    symbol=symbol,
                    action="BUY",
                    confidence=buy_confidence,
                    target_price=target_price,
                    stop_loss_price=stop_loss_price,
                    rationale=entry_rules
                ))
            elif should_sell:
                # For now, if sell signals, we propose to sell existing positions
                # In a real scenario, this would check existing positions and propose selling relevant quantity
                current_price = indicators_snapshot.current_price
                atr_value = indicators_snapshot.indicators.get('atr', None)
                atr_value = atr_value.value if atr_value else (current_price * 0.02)

                target_price = round(current_price * 0.95, 2)
                stop_loss_price = round(current_price + (atr_value * 2), 2)

                proposals.append(TradeProposal(
                    symbol=symbol,
                    action="SELL",
                    confidence=0.7, # Placeholder confidence for selling
                    target_price=target_price,
                    stop_loss_price=stop_loss_price,
                    rationale=exit_rules
                ))
        
        logger.debug(f"Generated {len(proposals)} proposals.")
        return proposals

    def __repr__(self) -> str:
        return f"<StrategyAgent(id='{self.agent_id}')>"
