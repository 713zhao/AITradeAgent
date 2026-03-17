import logging
import asyncio
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
    condition: str  # 'less_than', 'greater_than', 'crosses_above', 'above_indicator', etc.
    value: float  # threshold value (if comparing to number) or None if comparing to another indicator
    enabled: bool = True
    indicator2: Optional[str] = None  # second indicator for comparisons like 'greater_than_indicator'
    
    def __str__(self):
        if self.indicator2:
            return f"{self.name} ({self.type.value}): {self.indicator} {self.condition} {self.indicator2}"
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
                    value=rule_cfg.get('value', 0.0),
                    enabled=rule_cfg.get('enabled', True),
                    indicator2=rule_cfg.get('indicator2')
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
        
        Supports both single-indicator rules (value vs threshold) and
        two-indicator rules (indicator vs indicator2).
        """
        triggered = []
        
        for rule in self.entry_rules:
            if not rule.enabled:
                continue
            
            # Get primary indicator
            ind = indicators_snapshot.indicators.get(rule.indicator)
            if not ind:
                logger.warning(f"Rule {rule.name}: indicator {rule.indicator} not found")
                continue
            
            # Evaluate condition
            if rule.indicator2:
                # Compare two indicators
                ind2 = indicators_snapshot.indicators.get(rule.indicator2)
                if not ind2:
                    logger.warning(f"Rule {rule.name}: second indicator {rule.indicator2} not found")
                    continue
                if self._compare_two(ind.value, rule.condition, ind2.value):
                    triggered.append(rule.name)
            else:
                # Compare indicator value to threshold
                if self._check_condition(ind.value, rule.condition, rule.value):
                    triggered.append(rule.name)
        
        if not triggered:
            return False, 0.0, []
        
        enabled_entry_rules = [r for r in self.entry_rules if r.enabled]
        confidence = len(triggered) / len(enabled_entry_rules) if enabled_entry_rules else 0.0
        logger.info(f"Entry evaluation: {len(triggered)}/{len(enabled_entry_rules)} rules triggered (conf: {confidence:.2%})")
        return True, confidence, triggered
    
    def evaluate_exit(self, indicators_snapshot: IndicatorsSnapshot) -> Tuple[bool, List[str]]:
        """
        Evaluate exit rules against indicators
        
        Supports both single-indicator and two-indicator rules.
        """
        triggered = []
        
        for rule in self.exit_rules:
            if not rule.enabled:
                continue
            
            ind = indicators_snapshot.indicators.get(rule.indicator)
            if not ind:
                logger.warning(f"Rule {rule.name}: indicator {rule.indicator} not found")
                continue
            
            if rule.indicator2:
                ind2 = indicators_snapshot.indicators.get(rule.indicator2)
                if not ind2:
                    logger.warning(f"Rule {rule.name}: second indicator {rule.indicator2} not found")
                    continue
                if self._compare_two(ind.value, rule.condition, ind2.value):
                    triggered.append(rule.name)
            else:
                if self._check_condition(ind.value, rule.condition, rule.value):
                    triggered.append(rule.name)
        
        should_sell = len(triggered) > 0
        if should_sell:
            logger.info(f"Exit evaluation: {len(triggered)} rules triggered: {triggered}")
        return should_sell, triggered
    
    def _compare_two(self, val1: float, condition: str, val2: float) -> bool:
        """Compare two values based on condition."""
        if condition in ("greater_than", "above"):
            return val1 > val2
        elif condition in ("less_than", "below"):
            return val1 < val2
        elif condition == "equals":
            return abs(val1 - val2) < 0.001
        elif condition in ("greater_than_or_equal", "above_or_equal"):
            return val1 >= val2
        elif condition in ("less_than_or_equal", "below_or_equal"):
            return val1 <= val2
        else:
            logger.warning(f"Unknown two-indicator condition: {condition}")
            return False
    
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

    def __init__(self, config_engine):
        self.config_engine = config_engine
        self.event_bus = get_event_bus()
        self.portfolio_agent = None  # Will be injected by orchestrator
        
        # Load multiple strategy configurations from config
        self.strategies: Dict[str, Dict] = {}
        if hasattr(config_engine, 'get'):
            # Get the "strategies" map from finance config
            strategies_cfg = config_engine.get("finance", "strategies", default={})
            if isinstance(strategies_cfg, dict):
                for name, strat_cfg in strategies_cfg.items():
                    if not isinstance(strat_cfg, dict):
                        continue
                    entry_rules = strat_cfg.get('entry_rules', [])
                    exit_rules = strat_cfg.get('exit_rules', [])
                    all_rules = entry_rules + exit_rules
                    rule_strategy = RuleStrategy(all_rules)
                    
                    self.strategies[name] = {
                        'rule_strategy': rule_strategy,
                        'allocation': float(strat_cfg.get('allocation', 1.0)),
                        'risk_budget_pct': float(strat_cfg.get('risk_budget_pct', 1.0)),
                        'confidence_threshold': float(strat_cfg.get('confidence_threshold', 0.5)),
                        'entry_rules': entry_rules,
                        'exit_rules': exit_rules
                    }
                    logger.info(f"Loaded strategy '{name}': allocation={strat_cfg.get('allocation')}, risk={strat_cfg.get('risk_budget_pct')}%, threshold={strat_cfg.get('confidence_threshold')}")
        
        if not self.strategies:
            # Backward compatible fallback: single default strategy (rsi_macd)
            logger.warning("No strategies configured under finance/strategies. Falling back to default RSI+MACD.")
            default_entry = [
                Rule(name="rsi_oversold", type=RuleType.ENTRY, indicator="rsi", condition="less_than", value=35, enabled=True),
                Rule(name="macd_bullish", type=RuleType.ENTRY, indicator="macd", condition="greater_than", value=0, enabled=True)
            ]
            default_exit = [
                Rule(name="rsi_high", type=RuleType.EXIT, indicator="rsi", condition="greater_than", value=60, enabled=True)
            ]
            self.strategies['rsi_macd'] = {
                'rule_strategy': RuleStrategy([r.__dict__ for r in default_entry+default_exit]),
                'allocation': 1.0,
                'risk_budget_pct': 1.0,
                'confidence_threshold': 0.5,
                'entry_rules': default_entry,
                'exit_rules': default_exit
            }
        
        logger.info(f"StrategyAgent initialized with {len(self.strategies)} strategies")

    async def run(self, indicators_report: AgentReport, news_report: AgentReport) -> Optional[AgentReport]:
        """
        Generates trade proposals based on indicators and news.
        """
        logger.info("StrategyAgent run: Generating trade proposals.")
        
        try:
            trade_proposals = self._evaluate_strategies(indicators_report, news_report)

            if trade_proposals:
                message = f"{len(trade_proposals)} trade proposals generated."
                payload = {"proposals": [p.to_dict() for p in trade_proposals]}
                
                # Publish event asynchronously
                asyncio.create_task(self.event_bus.publish(Event(
                    event_type=Events.TRADE_PROPOSAL_GENERATED,
                    data=payload
                )))
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

    def _evaluate_strategies(self, indicators_report: AgentReport, news_report: AgentReport) -> List[TradeProposal]:
        """
        Evaluate all configured strategies and aggregate proposals.
        """
        from datetime import datetime
        
        proposals: List[TradeProposal] = []
        
        if not indicators_report or indicators_report.status != "success":
            return []
        
        payload = indicators_report.payload.copy()
        payload.pop('signals', None)
        
        # Reconstruct IndicatorResult objects
        indicators_data = payload.get('indicators', {})
        reconstructed_indicators = {}
        for name, ind_dict in indicators_data.items():
            ts = ind_dict.get('timestamp')
            if isinstance(ts, str):
                try:
                    ts = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                except:
                    ts = datetime.utcnow()
            else:
                ts = datetime.utcnow()
            signal = SignalType(ind_dict.get('signal', 'HOLD'))
            reconstructed_indicators[name] = IndicatorResult(
                name=ind_dict.get('name', name),
                value=ind_dict.get('value', 0.0),
                signal=signal,
                timestamp=ts,
                metadata=ind_dict.get('metadata', {})
            )
        
        # Add news sentiment as an indicator if available
        if news_report and news_report.status == "success":
            sentiment_payload = news_report.payload.get("sentiment", {})
            if isinstance(sentiment_payload, dict):
                symbol_news = sentiment_payload.get(symbol)
                if symbol_news:
                    overall = symbol_news.get("overall_sentiment")
                    if overall is not None:
                        # Signal: BUY if >0.3, SELL if <-0.3, else HOLD
                        if overall > 0.3:
                            news_signal = SignalType.BUY
                        elif overall < -0.3:
                            news_signal = SignalType.SELL
                        else:
                            news_signal = SignalType.HOLD
                        reconstructed_indicators["news_sentiment"] = IndicatorResult(
                            name="news_sentiment",
                            value=float(overall),
                            signal=news_signal,
                            timestamp=datetime.utcnow(),
                            metadata={"source": "news_agent"}
                        )
                        logger.debug(f"Added news_sentiment for {symbol}: {overall} ({news_signal.value})")
        
        payload['indicators'] = reconstructed_indicators
        ts = payload.get('timestamp')
        if isinstance(ts, str):
            try:
                payload['timestamp'] = datetime.fromisoformat(ts.replace('Z', '+00:00'))
            except:
                payload['timestamp'] = datetime.utcnow()
        
        indicators_snapshot = IndicatorsSnapshot(**payload)
        symbol = indicators_snapshot.symbol
        
        # Check existing position (global across strategies)
        has_position = False
        if self.portfolio_agent:
            pos = self.portfolio_agent.get_position(symbol)
            if pos:
                has_position = True
        
        # Current price
        current_price = indicators_snapshot.current_price
        if current_price is None:
            close_ind = reconstructed_indicators.get('close')
            current_price = close_ind.value if close_ind else 100.0
        
        # ATR for stops
        atr_value = reconstructed_indicators.get('atr')
        atr = atr_value.value if atr_value else (current_price * 0.02)
        
        # Evaluate each strategy
        for strategy_name, strat_cfg in self.strategies.items():
            rule_strategy = strat_cfg['rule_strategy']
            confidence_threshold = strat_cfg['confidence_threshold']
            risk_budget_pct = strat_cfg['risk_budget_pct']
            
            should_buy, buy_confidence, entry_rules_triggered = rule_strategy.evaluate_entry(indicators_snapshot)
            should_sell, exit_rules_triggered = rule_strategy.evaluate_exit(indicators_snapshot)
            
            rationale = []
            for r in entry_rules_triggered:
                rationale.append(f"{strategy_name}: entry {r}")
            for r in exit_rules_triggered:
                rationale.append(f"{strategy_name}: exit {r}")
            
            # BUY: entry triggered, no sell, no position, confidence OK
            if should_buy and not should_sell and not has_position and buy_confidence >= confidence_threshold:
                target_price = round(current_price * 1.05, 2)
                stop_loss_price = round(current_price - (atr * 2), 2)
                proposals.append(TradeProposal(
                    symbol=symbol,
                    action="BUY",
                    confidence=buy_confidence,
                    target_price=target_price,
                    stop_loss_price=stop_loss_price,
                    rationale=rationale,
                    strategy=strategy_name,
                    risk_budget_pct=risk_budget_pct
                ))
                logger.info(f"Strategy {strategy_name} generated BUY proposal for {symbol} (conf={buy_confidence:.2%})")
            
            # SELL: exit triggered and we have a position
            elif should_sell and has_position:
                target_price = round(current_price * 0.95, 2)
                stop_loss_price = round(current_price + (atr * 2), 2)
                proposals.append(TradeProposal(
                    symbol=symbol,
                    action="SELL",
                    confidence=0.7,
                    target_price=target_price,
                    stop_loss_price=stop_loss_price,
                    rationale=rationale,
                    strategy=strategy_name,
                    risk_budget_pct=risk_budget_pct
                ))
                logger.info(f"Strategy {strategy_name} generated SELL proposal for {symbol}")
        
        logger.debug(f"Generated {len(proposals)} proposals across {len(self.strategies)} strategies")
        return proposals

    def __repr__(self) -> str:
        return f"<StrategyAgent(id='{self.agent_id}')>"
