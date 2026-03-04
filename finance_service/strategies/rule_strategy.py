"""Rule-based trading strategy engine"""
from dataclasses import dataclass
from typing import Dict, List, Tuple
from enum import Enum
import logging

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
    
    def evaluate_entry(self, indicators_snapshot) -> Tuple[bool, float, List[str]]:
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
    
    def evaluate_exit(self, indicators_snapshot) -> Tuple[bool, List[str]]:
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
