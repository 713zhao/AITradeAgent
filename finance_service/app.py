"""Finance Service Application - Main orchestrator"""
import uuid
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from flask import Flask, request, jsonify

# Import all modules
from .core.config import Config
from .core.cache import Cache
from .core.logging import setup_logger, RunLogger
from .core.event_bus import event_bus
from .tools.openbb_tools import OpenBBTools
from .tools.indicator_tools import IndicatorTools
from .tools.risk_tools import RiskTools
from .strategies.baseline_rule_strategy import BaselineRuleStrategy
from .sim.portfolio import Portfolio
from .sim.execution import Execution
from .sim.metrics import Metrics
from .core.models import Decision

# Phase 2 imports
from .indicators.calculator import IndicatorCalculator
from .strategies.rule_strategy import RuleStrategy
from .strategies.decision_engine import DecisionEngine, DecisionContext

# Phase 3 imports
from .portfolio.portfolio_manager import PortfolioManager
from .portfolio.models import TradeStatus

# Phase 4 imports
from .risk.approval_engine import ApprovalEngine
from .risk.risk_enforcer import RiskEnforcer
from .risk.exposure_manager import ExposureManager
from .risk.models import RiskPolicy

# Phase 5 imports
from .execution.execution_engine import ExecutionEngine
from .execution.trade_monitor import TradeMonitor
from .execution.performance_reporter import PerformanceReporter

# Phase 6 imports
from .brokers.broker_manager import BrokerManager, BrokerMode

# Setup logging
logger = setup_logger(__name__)
run_logger = RunLogger()

# Initialize Flask app
app = Flask(__name__)

class FinanceService:
    """Main Finance Service orchestrator"""
    
    def __init__(self):
        self.cache = Cache()
        self.openbb = OpenBBTools()
        self.indicators = IndicatorTools()
        self.risk = RiskTools()
        self.strategy = BaselineRuleStrategy()
        self.portfolio = Portfolio()
        self.execution = Execution(self.portfolio)
        
        # Phase 2 components
        self.indicator_calc = IndicatorCalculator()
        try:
            rules_config = Config.get("finance", "strategies/entry_rules", [])
            self.strategy_engine = RuleStrategy(rules_config)
        except Exception as e:
            logger.warning(f"Could not load strategy rules: {e}, using empty rules")
            self.strategy_engine = RuleStrategy([])
        
        self.decision_engine = DecisionEngine()
        
        # Phase 3 components
        initial_cash = Config.DEFAULT_INITIAL_CASH
        self.portfolio_manager = PortfolioManager(initial_cash=initial_cash)
        
        # Phase 4 components
        self.approval_engine = ApprovalEngine(approval_timeout_hours=1)
        self.risk_enforcer = RiskEnforcer()
        self.exposure_manager = ExposureManager()
        
        # Load risk policy from config if available
        try:
            policy_config = Config.get("finance", "risk_policy", {})
            if policy_config:
                risk_policy = RiskPolicy(
                    policy_id=policy_config.get("id", "STANDARD"),
                    policy_name=policy_config.get("name", "Standard Risk Policy"),
                    max_positions=policy_config.get("max_positions", 20),
                    max_position_size_pct=policy_config.get("max_position_size_pct", 10.0),
                    max_sector_exposure_pct=policy_config.get("max_sector_exposure_pct", 25.0),
                    max_portfolio_leverage=policy_config.get("max_portfolio_leverage", 2.0),
                    max_daily_loss_pct=policy_config.get("max_daily_loss_pct", 5.0),
                    max_drawdown_pct=policy_config.get("max_drawdown_pct", 20.0),
                    approval_required_pct=policy_config.get("approval_required_pct", 0.75),
                )
                self.risk_enforcer.set_policy(risk_policy)
        except Exception as e:
            logger.warning(f"Could not load risk policy: {e}, using default policy")
        
        # Phase 5 components
        self.execution_engine = ExecutionEngine()
        self.trade_monitor = TradeMonitor()
        self.performance_reporter = PerformanceReporter()
        
        # Phase 6 components
        # Initialize broker manager (paper trading by default)
        try:
            broker_mode_str = Config.get("finance", "broker_mode", "paper").lower()
            broker_mode = BrokerMode.PAPER if broker_mode_str == "paper" else BrokerMode.LIVE
            
            # Get broker configuration
            initial_cash = Config.get("finance", "initial_cash", 100000.0)
            api_key = Config.get("finance", "alpaca_api_key", None)
            api_secret = Config.get("finance", "alpaca_api_secret", None)
            alpaca_base_url = Config.get("finance", "alpaca_base_url", "https://paper-api.alpaca.markets")
            
            self.broker_manager = BrokerManager(
                mode=broker_mode,
                initial_cash=initial_cash,
                api_key=api_key,
                api_secret=api_secret,
                alpaca_base_url=alpaca_base_url,
                slippage_bps=Config.get("finance", "broker_slippage_bps", 1.0),
                fill_delay_seconds=Config.get("finance", "broker_fill_delay_seconds", 0.1),
            )
            
            # Register broker event listeners
            self.broker_manager.register_event_listener("ORDER_FILLED", self._on_order_filled)
            self.broker_manager.register_event_listener("POSITION_CLOSED", self._on_position_closed)
            
            # Update ExecutionEngine with broker manager
            self.execution_engine.broker_manager = self.broker_manager
            
            logger.info(f"Broker manager initialized ({broker_mode.value} mode)")
        
        except Exception as e:
            logger.warning(f"Could not initialize broker manager: {e}, Operating without live brokers")
            self.broker_manager = None
        
        # Register event listeners
        event_bus.on("DATA_READY", self._on_data_ready)
        event_bus.on("DECISION_MADE", self._on_decision_made)
        event_bus.on("TRADE_OPENED", self._on_trade_opened)
        event_bus.on("APPROVAL_REQUIRED", self._on_approval_required)
        event_bus.on("TRADE_APPROVED", self._on_trade_approved)
        
        logger.info("Finance Service initialized (with Phase 0-5 components)")
    
    def _on_data_ready(self, event: Any):
        """
        Handle DATA_READY event from Phase 1 DataManager
        Flow: Get data → Calculate indicators → Evaluate rules → Make decision → Emit DECISION_MADE
        
        Args:
            event: Event object (can be Event class or dict)
        """
        try:
            # Handle both Event objects and dicts
            if isinstance(event, dict):
                symbol = event.get('data', {}).get('symbol') or event.get('symbol')
                interval = event.get('data', {}).get('interval') or event.get('interval', '1d')
            else:
                # assume it's an Event object
                symbol = event.data.get('symbol') if hasattr(event, 'data') else None
                interval = event.data.get('interval', '1d') if hasattr(event, 'data') else '1d'
            
            if not symbol:
                logger.warning(f"DATA_READY event without symbol: {event}")
                return
            
            logger.info(f"DATA_READY received for {symbol} ({interval})")
            
            # Get OHLCV data (from cache or new fetch)
            price_data = self.get_price_historical(symbol)
            
            if "error" in price_data:
                logger.error(f"Failed to fetch data for {symbol}: {price_data['error']}")
                event_bus.publish({
                    'type': 'ANALYSIS_FAILED',
                    'symbol': symbol,
                    'error': price_data['error'],
                    'timestamp': datetime.utcnow().isoformat()
                })
                return
            
            # Convert to DataFrame for indicator calculation
            import pandas as pd
            import numpy as np
            
            closes = np.array(price_data.get("close", []))
            highs = np.array(price_data.get("high", []))
            lows = np.array(price_data.get("low", []))
            volumes = np.array(price_data.get("volume", []))
            timestamps = pd.date_range(end=pd.Timestamp.now(), periods=len(closes), freq='D')
            
            df = pd.DataFrame({
                'open': price_data.get("open", highs),
                'high': highs,
                'low': lows,
                'close': closes,
                'volume': volumes
            }, index=timestamps)
            
            # Calculate all indicators
            ind_snapshot = self.indicator_calc.calculate_all(df, symbol)
            
            # Evaluate strategy rules
            entry_triggered, entry_conf, entry_rules = self.strategy_engine.evaluate_entry(ind_snapshot)
            exit_triggered, exit_rules = self.strategy_engine.evaluate_exit(ind_snapshot)
            
            # Build decision context
            atr_value = ind_snapshot.indicators.get('atr', None)
            atr = atr_value.value if atr_value else 0.0
            current_price = float(closes[-1])
            
            context = DecisionContext(
                symbol=symbol,
                current_price=current_price,
                atr=atr,
                entry_triggered=entry_triggered,
                entry_confidence=entry_conf,
                entry_rules=entry_rules,
                exit_triggered=exit_triggered,
                exit_rules=exit_rules,
                all_signals=ind_snapshot.get_all_signals()
            )
            
            # Make decision
            decision = self.decision_engine.make_decision(context)
            
            # Emit DECISION_MADE event
            event_bus.publish({
                'type': 'DECISION_MADE',
                'symbol': symbol,
                'decision': decision.to_dict() if hasattr(decision, 'to_dict') else decision,
                'timestamp': datetime.utcnow().isoformat()
            })
            
            logger.info(f"DECISION_MADE published for {symbol}: {decision.decision}")
            
        except Exception as e:
            logger.error(f"Error processing DATA_READY event: {e}", exc_info=True)
            event_bus.publish({
                'type': 'ANALYSIS_FAILED',
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            })

    def _on_decision_made(self, event: Any):
        """
        Handle DECISION_MADE event from Phase 2 DecisionEngine
        Flow: Decision received → Create trade in portfolio → Update positions
        
        Args:
            event: Event object (can be Event class or dict)
        """
        try:
            # Handle both Event objects and dicts
            if isinstance(event, dict):
                symbol = event.get('data', {}).get('symbol') or event.get('symbol')
                decision_obj = event.get('data', {}).get('decision') or event.get('decision')
                task_id = event.get('data', {}).get('task_id') or event.get('task_id', 'UNKNOWN')
            else:
                # Assume it's an Event object
                symbol = event.data.get('symbol') if hasattr(event, 'data') else None
                decision_obj = event.data.get('decision') if hasattr(event, 'data') else None
                task_id = event.data.get('task_id', 'UNKNOWN') if hasattr(event, 'data') else 'UNKNOWN'
            
            if not symbol or not decision_obj:
                logger.warning(f"DECISION_MADE event missing symbol or decision: {event}")
                return
            
            logger.info(f"DECISION_MADE received for {symbol}: {decision_obj.get('decision', 'UNKNOWN')}")
            
            # Get current price (from last decision or quote)
            current_price = decision_obj.get('price', 0.0)
            if not current_price:
                # Try to fetch current quote
                quote = self.get_quote(symbol)
                current_price = float(quote.get('price', 0.0)) if quote else 0.0
            
            # Extract decision details
            decision_type = decision_obj.get('decision', 'HOLD')  # BUY, SELL, HOLD
            confidence = decision_obj.get('confidence', 0.0)
            stop_loss = decision_obj.get('stop_loss')
            take_profit = decision_obj.get('take_profit')
            reason = decision_obj.get('reason', 'Decision Engine')
            
            # Execute trade based on decision
            trade = None
            if decision_type == "BUY":
                # Default size: 10 shares (can be configurable)
                qty = Config.get("finance", "portfolio/position_size_shares", 10)
                trade = self.portfolio_manager.execute_buy(
                    task_id=task_id,
                    symbol=symbol,
                    quantity=qty,
                    price=current_price,
                    decision=decision_obj,
                    confidence=confidence,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    reason=reason,
                )
                
                # Simulate immediate fill in paper trading
                self.portfolio_manager.fill_trade(trade.trade_id)
                
                # Emit TRADE_OPENED event
                event_bus.publish({
                    'type': 'TRADE_OPENED',
                    'symbol': symbol,
                    'trade_id': trade.trade_id,
                    'side': 'BUY',
                    'quantity': qty,
                    'price': current_price,
                    'stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'timestamp': datetime.utcnow().isoformat()
                })
                
            elif decision_type == "SELL":
                # Check if we have a position to sell
                position = self.portfolio_manager.get_position(symbol)
                if position and position.quantity > 0:
                    trade = self.portfolio_manager.execute_sell(
                        task_id=task_id,
                        symbol=symbol,
                        quantity=position.quantity,  # Sell entire position
                        price=current_price,
                        decision=decision_obj,
                        confidence=confidence,
                        stop_loss=stop_loss,
                        take_profit=take_profit,
                        reason=reason,
                    )
                    
                    # Simulate immediate fill
                    self.portfolio_manager.fill_trade(trade.trade_id)
                    
                    # Emit TRADE_CLOSED event
                    event_bus.publish({
                        'type': 'TRADE_CLOSED',
                        'symbol': symbol,
                        'trade_id': trade.trade_id,
                        'side': 'SELL',
                        'quantity': position.quantity,
                        'price': current_price,
                        'pnl': position.unrealized_pnl(),
                        'timestamp': datetime.utcnow().isoformat()
                    })
                else:
                    logger.warning(f"SELL decision for {symbol} but no position to close")
            
            else:
                # HOLD decision - no action
                logger.info(f"HOLD decision for {symbol}, no trade executed")
            
            # Emit PORTFOLIO_UPDATED event with current metrics
            equity_metrics = self.portfolio_manager.get_equity_metrics()
            event_bus.publish({
                'type': 'PORTFOLIO_UPDATED',
                'symbol': symbol,
                'metrics': equity_metrics,
                'timestamp': datetime.utcnow().isoformat()
            })
            
        except Exception as e:
            logger.error(f"Error processing DECISION_MADE event: {e}", exc_info=True)
            event_bus.publish({
                'type': 'TRADE_FAILED',
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            })

    def _on_trade_opened(self, event: Any):
        """
        Handle TRADE_OPENED event from Phase 3 PortfolioManager
        Flow: Trade opened → Risk check → Approval request or execution
        
        Args:
            event: Event object (can be Event class or dict)
        """
        try:
            # Handle both Event objects and dicts
            if isinstance(event, dict):
                symbol = event.get('data', {}).get('symbol') or event.get('symbol')
                trade_id = event.get('data', {}).get('trade_id') or event.get('trade_id')
                side = event.get('data', {}).get('side') or event.get('side')
                quantity = event.get('data', {}).get('quantity') or event.get('quantity', 0)
                price = event.get('data', {}).get('price') or event.get('price', 0)
            else:
                # Assume it's an Event object
                symbol = event.data.get('symbol') if hasattr(event, 'data') else None
                trade_id = event.data.get('trade_id') if hasattr(event, 'data') else None
                side = event.data.get('side', 'BUY') if hasattr(event, 'data') else 'BUY'
                quantity = event.data.get('quantity', 0) if hasattr(event, 'data') else 0
                price = event.data.get('price', 0) if hasattr(event, 'data') else 0
            
            if not symbol or not trade_id:
                logger.warning(f"TRADE_OPENED event missing symbol or trade_id: {event}")
                return
            
            logger.info(f"TRADE_OPENED received: {trade_id} {symbol} {quantity}@{price}")
            
            # Get trade from portfolio manager
            trade = self.portfolio_manager.get_trade(trade_id)
            if not trade:
                logger.error(f"Trade not found in portfolio: {trade_id}")
                return
            
            # Perform risk checks
            portfolio = self.portfolio_manager.get_portfolio()
            current_positions = {
                pos.symbol: pos.quantity
                for pos in self.portfolio_manager.get_positions()
            }
            
            confidence = trade.confidence if hasattr(trade, 'confidence') else 1.0
            risk_check = self.risk_enforcer.check_trade(
                trade_id=trade_id,
                symbol=symbol,
                quantity=quantity,
                price=price,
                portfolio_equity=portfolio.total_equity(),
                current_positions=current_positions,
                confidence=confidence,
            )
            
            # Check if approval is needed
            if risk_check.violations_count() > 0 or risk_check.approval_required:
                # Create approval request
                approval_request = self.approval_engine.create_approval_request(
                    trade_id=trade_id,
                    symbol=symbol,
                    trade_details={
                        'side': side,
                        'quantity': quantity,
                        'price': price,
                        'confidence': confidence,
                        'stop_loss': trade.stop_loss if hasattr(trade, 'stop_loss') else None,
                        'take_profit': trade.take_profit if hasattr(trade, 'take_profit') else None,
                    },
                    risk_check=risk_check,
                    reason=f"Risk violations: {[l.limit_type for l in risk_check.violated_limits]}",
                )
                
                # Emit approval request event
                event_bus.publish({
                    'type': 'APPROVAL_REQUIRED',
                    'trade_id': trade_id,
                    'approval_request_id': approval_request.request_id,
                    'symbol': symbol,
                    'risk_score': risk_check.risk_score,
                    'violations': [l.limit_type for l in risk_check.violated_limits],
                    'timestamp': datetime.utcnow().isoformat()
                })
                
                logger.warning(f"Approval required for trade {trade_id}: risk_score={risk_check.risk_score:.1f}")
            else:
                # Risk check passed, trade can proceed
                logger.info(f"Risk check passed for trade {trade_id}: risk_score={risk_check.risk_score:.1f}")
                
                # Emit trade approved event
                event_bus.publish({
                    'type': 'TRADE_APPROVED',
                    'trade_id': trade_id,
                    'symbol': symbol,
                    'risk_score': risk_check.risk_score,
                    'timestamp': datetime.utcnow().isoformat()
                })
            
        except Exception as e:
            logger.error(f"Error processing TRADE_OPENED event: {e}", exc_info=True)
            event_bus.publish({
                'type': 'RISK_CHECK_FAILED',
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            })

    def _on_approval_required(self, event: Any):
        """
        Handle APPROVAL_REQUIRED event from Phase 4 RiskEnforcer
        Flow: Risk violations detected → Awaiting manual approval
        
        Args:
            event: Event object (can be Event class or dict)
        """
        try:
            # Handle both Event objects and dicts
            if isinstance(event, dict):
                trade_id = event.get('data', {}).get('trade_id') or event.get('trade_id')
                symbol = event.get('data', {}).get('symbol') or event.get('symbol')
                approval_request_id = event.get('data', {}).get('approval_request_id') or event.get('approval_request_id')
            else:
                # Assume it's an Event object
                trade_id = event.data.get('trade_id') if hasattr(event, 'data') else None
                symbol = event.data.get('symbol') if hasattr(event, 'data') else None
                approval_request_id = event.data.get('approval_request_id') if hasattr(event, 'data') else None
            
            if not trade_id or not approval_request_id:
                logger.warning(f"APPROVAL_REQUIRED event missing trade_id or approval_request_id: {event}")
                return
            
            logger.info(f"APPROVAL_REQUIRED received: {trade_id} {symbol}, request_id={approval_request_id}")
            
            # In a real system, this would trigger manual approval workflow (Telegram, dashboard, etc.)
            # For now, we log the pending approval request
            approval_request = self.approval_engine.get_request(approval_request_id)
            if approval_request:
                logger.warning(f"Approval request pending: {approval_request_id} for {symbol}")
                logger.warning(f"Pending approvals: {self.approval_engine.pending_approval_count()}")
            
        except Exception as e:
            logger.error(f"Error processing APPROVAL_REQUIRED event: {e}", exc_info=True)

    def _on_trade_approved(self, event: Any):
        """
        Handle TRADE_APPROVED event from Phase 4 RiskEnforcer
        Flow: Risk check passed → Add to monitor → Await execution → Track SL/TP
        
        Args:
            event: Event object (can be Event class or dict)
        """
        try:
            # Handle both Event objects and dicts
            if isinstance(event, dict):
                trade_id = event.get('data', {}).get('trade_id') or event.get('trade_id')
                symbol = event.get('data', {}).get('symbol') or event.get('symbol')
            else:
                # Assume it's an Event object
                trade_id = event.data.get('trade_id') if hasattr(event, 'data') else None
                symbol = event.data.get('symbol') if hasattr(event, 'data') else None
            
            if not trade_id:
                logger.warning(f"TRADE_APPROVED event missing trade_id: {event}")
                return
            
            logger.info(f"TRADE_APPROVED received: {trade_id} {symbol}")
            
            # Get trade from portfolio manager
            trade = self.portfolio_manager.get_trade(trade_id)
            if not trade:
                logger.error(f"Trade not found in portfolio: {trade_id}")
                return
            
            # Create execution context and auto-execute
            risk_check_result = {
                'approval_required': False,
                'risk_score': 35.0,
                'violated_limits': [],
            }
            
            exec_context = self.execution_engine.create_execution_context(
                trade_id=trade_id,
                symbol=symbol,
                side=trade.side,
                quantity=trade.quantity,
                target_price=trade.price,
                confidence=trade.confidence if hasattr(trade, 'confidence') else 1.0,
                risk_assessment=risk_check_result,
            )
            
            # Auto-execute the trade
            exec_report = self.execution_engine.approve_and_execute(trade_id)
            
            logger.info(f"Trade executed: {exec_report.execution_id}")
            
            # Add to trade monitor for SL/TP tracking
            self.trade_monitor.add_trade(
                trade_id=trade_id,
                symbol=symbol,
                side=trade.side,
                entry_price=trade.price,
                entry_quantity=trade.quantity,
                stop_loss=trade.stop_loss if hasattr(trade, 'stop_loss') else trade.price * 0.95,
                take_profit=trade.take_profit if hasattr(trade, 'take_profit') else trade.price * 1.05,
            )
            
            # Emit EXECUTION_REPORT event
            event_bus.publish({
                'type': 'EXECUTION_REPORT',
                'execution_id': exec_report.execution_id,
                'trade_id': trade_id,
                'symbol': symbol,
                'status': exec_report.status,
                'filled_price': exec_report.filled_price,
                'filled_quantity': exec_report.filled_quantity,
                'execution_type': exec_report.execution_type.value,
                'timestamp': datetime.utcnow().isoformat()
            })
            
        except Exception as e:
            logger.error(f"Error processing TRADE_APPROVED event: {e}", exc_info=True)
            event_bus.publish({
                'type': 'EXECUTION_FAILED',
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            })

    def _on_order_filled(self, data: Dict[str, Any]):
        """
        Handle ORDER_FILLED event from Phase 6 BrokerManager
        
        Args:
            data: Event data dict with order details
        """
        try:
            order_id = data.get('order_id')
            trade_id = data.get('trade_id')
            symbol = data.get('symbol')
            fill_price = data.get('fill_price')
            quantity = data.get('quantity')
            
            logger.info(
                f"ORDER_FILLED: {order_id} - {symbol} {quantity} @ ${fill_price:.2f} (trade_id: {trade_id})"
            )
            
            # Publish event through event bus for other components
            event_bus.publish({
                'type': 'ORDER_FILLED',
                'order_id': order_id,
                'trade_id': trade_id,
                'symbol': symbol,
                'fill_price': fill_price,
                'quantity': quantity,
                'timestamp': datetime.utcnow().isoformat()
            })
        
        except Exception as e:
            logger.error(f"Error processing ORDER_FILLED event: {e}")
    
    def _on_position_closed(self, data: Dict[str, Any]):
        """
        Handle POSITION_CLOSED event from Phase 6 BrokerManager
        
        Args:
            data: Event data dict with position details
        """
        try:
            symbol = data.get('symbol')
            order_id = data.get('order_id')
            
            logger.info(f"POSITION_CLOSED: {symbol} with order {order_id}")
            
            # Publish event through event bus
            event_bus.publish({
                'type': 'POSITION_CLOSED',
                'symbol': symbol,
                'order_id': order_id,
                'timestamp': datetime.utcnow().isoformat()
            })
        
        except Exception as e:
            logger.error(f"Error processing POSITION_CLOSED event: {e}")

    
    # =====================
    # DATA TOOLS
    # =====================
    
    def get_price_historical(self, symbol: str, start_date: Optional[str] = None,
                            end_date: Optional[str] = None,
                            interval: str = "1day") -> Dict[str, Any]:
        """Fetch historical prices"""
        return self.openbb.get_price_historical(symbol, start_date, end_date, interval)
    
    def get_fundamentals(self, symbol: str, statement_type: str = "income") -> Dict[str, Any]:
        """Fetch fundamental financial data"""
        return self.openbb.get_fundamentals(symbol, statement_type)
    
    def get_company_profile(self, symbol: str) -> Dict[str, Any]:
        """Fetch company profile"""
        return self.openbb.get_company_profile(symbol)
    
    def get_quote(self, symbol: str) -> Dict[str, Any]:
        """Fetch latest quote"""
        return self.openbb.get_quote(symbol)
    
    # =====================
    # INDICATOR TOOLS
    # =====================
    
    def calc_rsi(self, prices: List[float], period: int = 14) -> List[float]:
        """Calculate RSI"""
        return self.indicators.calc_rsi(prices, period)
    
    def calc_macd(self, prices: List[float], fast: int = 12,
                 slow: int = 26, signal: int = 9) -> Dict[str, List[float]]:
        """Calculate MACD"""
        return self.indicators.calc_macd(prices, fast, slow, signal)
    
    def calc_sma(self, prices: List[float], window: int = 20) -> List[float]:
        """Calculate SMA"""
        return self.indicators.calc_sma(prices, window)
    
    def calc_ema(self, prices: List[float], window: int = 20) -> List[float]:
        """Calculate EMA"""
        return self.indicators.calc_ema(prices, window)
    
    def calc_atr(self, highs: List[float], lows: List[float],
                closes: List[float], period: int = 14) -> List[float]:
        """Calculate ATR"""
        return self.indicators.calc_atr(highs, lows, closes, period)
    
    def calc_bollinger_bands(self, prices: List[float], window: int = 20,
                            num_std: float = 2) -> Dict[str, List[float]]:
        """Calculate Bollinger Bands"""
        return self.indicators.calc_bollinger_bands(prices, window, num_std)
    
    # =====================
    # RISK TOOLS
    # =====================
    
    def calc_position_size(self, symbol: str, current_price: float,
                          atr: Optional[float] = None,
                          portfolio_equity: float = 100000) -> Dict[str, Any]:
        """Calculate position size based on ATR and risk budget"""
        return self.risk.calc_position_size(symbol, current_price, atr, portfolio_equity)
    
    def validate_trade(self, symbol: str, action: str, qty: float,
                      price: float, policy: Optional[Dict] = None) -> Dict[str, Any]:
        """Validate trade against risk policies"""
        return self.risk.validate_trade(
            symbol, action, qty, price,
            self.portfolio.total_value,
            self.portfolio.positions,
            policy
        )
    
    # =====================
    # ANALYSIS & STRATEGY
    # =====================
    
    def analyze(self, symbol: str, lookback_days: Optional[int] = None) -> Dict[str, Any]:
        """
        Full analysis: fetch data, compute indicators, run strategy
        
        Returns:
            Complete analysis with signals and decision
        """
        task_id = str(uuid.uuid4())
        
        try:
            # Fetch price data
            price_data = self.get_price_historical(symbol)
            
            if "error" in price_data:
                logger.error(f"Failed to fetch data for {symbol}: {price_data['error']}")
                return {
                    "error": price_data["error"],
                    "task_id": task_id,
                    "symbol": symbol,
                }
            
            # Extract OHLCV
            closes = price_data.get("close", [])
            highs = price_data.get("high", [])
            lows = price_data.get("low", [])
            
            if not closes or len(closes) < 50:
                logger.warning(f"Insufficient data points for {symbol}")
                return {
                    "error": "Insufficient historical data",
                    "task_id": task_id,
                    "symbol": symbol,
                }
            
            # Compute indicators
            rsi = self.calc_rsi(closes, 14)
            sma50 = self.calc_sma(closes, 50)
            atr = self.calc_atr(highs, lows, closes, 14)
            
            # Build data dict for strategy
            analysis_data = {
                "close": closes,
                "high": highs,
                "low": lows,
                "rsi": rsi[-len(sma50):] if len(rsi) >= len(sma50) else rsi,
                "sma50": sma50,
                "atr": atr[-len(sma50):] if len(atr) >= len(sma50) else atr,
            }
            
            # Run strategy
            strategy_result = self.strategy.analyze(
                symbol,
                analysis_data,
                portfolio_equity=self.portfolio.total_value,
                existing_position=self.portfolio.get_position(symbol)
            )
            
            # Add metadata
            strategy_result.update({
                "task_id": task_id,
                "timestamp": datetime.utcnow().isoformat(),
                "required_approval": strategy_result.get("decision") != "HOLD",
            })
            
            # Log the run
            import json
            run_logger.log_run(
                task_id=task_id,
                symbol=symbol,
                decision_json=json.dumps(strategy_result),
            )
            
            logger.info(f"Analysis complete: {symbol} -> {strategy_result.get('decision')}")
            return strategy_result
        
        except Exception as e:
            logger.error(f"Analysis failed for {symbol}: {str(e)}", exc_info=True)
            return {
                "error": str(e),
                "task_id": task_id,
                "symbol": symbol,
            }
    
    # =====================
    # PORTFOLIO & EXECUTION
    # =====================
    
    def portfolio_get_state(self) -> Dict[str, Any]:
        """Get current portfolio state"""
        return self.portfolio.get_state()
    
    def portfolio_propose_trade(self, decision: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and propose a trade (dry-run)"""
        # Convert to Decision object if needed
        if isinstance(decision, dict):
            decision_obj = Decision(**decision)
        else:
            decision_obj = decision
        
        valid, summary, details = self.execution.propose_trade(decision_obj)
        
        return {
            "task_id": decision_obj.task_id,
            "valid": valid,
            "summary": summary,
            "details": details,
        }
    
    def portfolio_execute_trade(self, task_id: str, approval_id: str = "") -> Dict[str, Any]:
        """Execute a proposed trade"""
        success, msg = self.execution.execute_trade(task_id, approval_id)
        
        return {
            "task_id": task_id,
            "success": success,
            "message": msg,
            "portfolio_state": self.portfolio.get_state()
        }
    
    def portfolio_mark_to_market(self, prices: Dict[str, float]):
        """Update portfolio prices"""
        self.portfolio.update_prices(prices)
        
        # Take snapshot
        self.portfolio.snapshot()
        
        return {"updated": list(prices.keys())}
    
    def portfolio_get_performance(self) -> Dict[str, Any]:
        """Get portfolio performance metrics"""
        return Metrics.summary(self.portfolio)
    
    def portfolio_reset(self):
        """Reset portfolio to initial state"""
        self.portfolio.reset()
        return {"status": "reset"}


# Initialize service
finance_service = FinanceService()


# =====================
# FLASK ROUTES
# =====================

@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint"""
    return jsonify({"status": "ok", "service": "finance"}), 200


@app.route("/analyze", methods=["POST"])
def analyze():
    """
    POST /analyze
    Body: {"symbol": "AAPL"}
    """
    data = request.get_json() or {}
    symbol = data.get("symbol", "").upper()
    
    if not symbol:
        return jsonify({"error": "Missing symbol parameter"}), 400
    
    result = finance_service.analyze(symbol)
    return jsonify(result), 200


@app.route("/portfolio/state", methods=["GET"])
def get_portfolio_state():
    """Get current portfolio state"""
    return jsonify(finance_service.portfolio_get_state()), 200


@app.route("/portfolio/propose", methods=["POST"])
def propose_trade():
    """Propose a trade"""
    data = request.get_json() or {}
    result = finance_service.portfolio_propose_trade(data)
    return jsonify(result), 200


@app.route("/portfolio/execute", methods=["POST"])
def execute_trade():
    """Execute a proposed trade"""
    data = request.get_json() or {}
    task_id = data.get("task_id")
    approval_id = data.get("approval_id", "")
    
    if not task_id:
        return jsonify({"error": "Missing task_id"}), 400
    
    result = finance_service.portfolio_execute_trade(task_id, approval_id)
    return jsonify(result), 200


@app.route("/quote/<symbol>", methods=["GET"])
def get_quote(symbol):
    """Get latest quote for symbol"""
    result = finance_service.get_quote(symbol.upper())
    return jsonify(result), 200


if __name__ == "__main__":
    Config.validate()
    app.run(host="0.0.0.0", port=5000, debug=True)
