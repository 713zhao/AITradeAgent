"""
Multi-Broker Manager

This module provides unified management across multiple broker APIs,
enabling cross-broker operations, intelligent routing, and consolidated portfolio management.

Key Features:
- Multi-broker order routing and execution
- Cross-broker portfolio consolidation
- Intelligent broker selection based on symbol availability
- Unified risk management across brokers
- Broker failover and redundancy
- Performance monitoring and load balancing

Author: PicotradeAgent
Version: 6.3.0
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Union, Type
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
import json

# Import all broker implementations
from finance_service.brokers.alpaca_broker import AlpacaBroker, AlpacaConfig
from finance_service.brokers.paper_broker import PaperBroker, PaperConfig
from finance_service.brokers.ibkr_broker import IBKRBroker, IBKRConfig
from finance_service.brokers.tda_broker import TDABroker, TDAConfig
from finance_service.brokers.binance_broker import BinanceBroker, BinanceConfig
from finance_service.brokers.coinbase_broker import CoinbaseBroker, CoinbaseConfig

from finance_service.brokers.base_broker import BaseBroker, OrderResult, Position, AccountInfo, MarketData
from finance_service.brokers.base_broker import OrderSide, OrderType, OrderStatus, AssetType
from finance_service.core.events import Event, EventType, EventManager
from finance_service.core.data_types import OrderRequest, PositionRequest, AccountRequest


class BrokerType(str, Enum):
    """Supported broker types"""
    ALPACA = "ALPACA"
    PAPER = "PAPER"
    IBKR = "IBKR"
    TDA = "TDA"
    BINANCE = "BINANCE"
    COINBASE = "COINBASE"


class RoutingStrategy(str, Enum):
    """Order routing strategies"""
    ROUND_ROBIN = "ROUND_ROBIN"
    BEST_PRICE = "BEST_PRICE"
    LEAST_LOAD = "LEAST_LOAD"
    PREFERRED = "PREFERRED"
    FAILOVER = "FAILOVER"


class AssetClass(str, Enum):
    """Asset classes for routing logic"""
    STOCK = "STOCK"
    OPTION = "OPTION"
    FUTURE = "FUTURE"
    FOREX = "FOREX"
    CRYPTO = "CRYPTO"
    BOND = "BOND"
    ETF = "ETF"


@dataclass
class BrokerCapability:
    """Broker capability specification"""
    broker_type: BrokerType
    asset_classes: List[AssetClass]
    order_types: List[OrderType]
    time_in_force: List[str]
    max_position_size: float
    min_order_size: float
    max_order_size: float
    supported_symbols: List[str]
    market_hours: Dict[str, str]  # day -> hours
    commission_rate: float
    latency_ms: int
    reliability_score: float  # 0.0 to 1.0


@dataclass
class RoutingRule:
    """Order routing rule"""
    name: str
    asset_class: AssetClass
    symbol_patterns: List[str]
    preferred_brokers: List[BrokerType]
    strategy: RoutingStrategy
    max_latency_ms: int
    min_reliability_score: float
    enabled: bool = True


@dataclass
class MultiBrokerConfig:
    """Multi-broker configuration"""
    # Broker configurations
    alpaca_config: Optional[AlpacaConfig] = None
    paper_config: Optional[PaperConfig] = None
    ibkr_config: Optional[IBKRConfig] = None
    tda_config: Optional[TDAConfig] = None
    binance_config: Optional[BinanceConfig] = None
    coinbase_config: Optional[CoinbaseConfig] = None
    
    # Routing configuration
    routing_strategy: RoutingStrategy = RoutingStrategy.BEST_PRICE
    routing_rules: List[RoutingRule] = field(default_factory=list)
    
    # Broker management
    enabled_brokers: List[BrokerType] = field(default_factory=lambda: [BrokerType.ALPACA, BrokerType.PAPER])
    primary_brokers: Dict[AssetClass, BrokerType] = field(default_factory=dict)
    fallback_order: List[BrokerType] = field(default_factory=list)
    
    # Performance settings
    connection_timeout: int = 30
    order_timeout: int = 60
    health_check_interval: int = 60
    load_balancing: bool = True
    
    # Risk management
    max_total_exposure: float = 1000000.0
    max_single_position: float = 100000.0
    max_daily_orders: int = 1000
    
    # Logging
    log_level: str = "INFO"
    log_routing_decisions: bool = True


@dataclass
class BrokerHealthStatus:
    """Broker health status"""
    broker_type: BrokerType
    connected: bool
    last_heartbeat: Optional[datetime]
    latency_ms: float
    error_rate: float
    orders_today: int
    last_error: Optional[str]
    reliability_score: float
    
    def is_healthy(self) -> bool:
        return (self.connected and 
                self.latency_ms < 1000 and 
                self.error_rate < 0.1 and 
                self.reliability_score > 0.8)


class MultiBrokerManager:
    """
    Multi-Broker Manager
    
    Provides unified management across multiple brokers with intelligent routing,
    cross-broker portfolio management, and failover capabilities.
    """
    
    def __init__(self, config: MultiBrokerConfig, event_manager: EventManager):
        self.config = config
        self.event_manager = event_manager
        self.logger = logging.getLogger(f"{__name__}.MultiBrokerManager")
        
        # Broker instances
        self.brokers: Dict[BrokerType, BaseBroker] = {}
        self.broker_capabilities: Dict[BrokerType, BrokerCapability] = {}
        self.broker_health: Dict[BrokerType, BrokerHealthStatus] = {}
        
        # Portfolio management
        self.cross_broker_portfolio: Dict[str, Position] = {}
        self.total_positions_value: float = 0.0
        self.daily_order_count: int = 0
        
        # Routing state
        self.routing_decisions: List[Dict[str, Any]] = []
        self.last_routing_time: Dict[BrokerType, datetime] = {}
        
        # Threading and async support
        self.executor = ThreadPoolExecutor(max_workers=5)
        self._shutdown_event = asyncio.Event()
        
        # Performance tracking
        self.performance_stats: Dict[str, Any] = {}
        
        self.logger.info("Multi-Broker Manager initialized")
    
    async def initialize(self) -> bool:
        """
        Initialize all brokers
        
        Returns:
            bool: True if initialization successful
        """
        try:
            self.logger.info("Initializing multi-broker system")
            
            success = True
            initialized_brokers = []
            
            # Initialize each enabled broker
            for broker_type in self.config.enabled_brokers:
                try:
                    if await self._initialize_broker(broker_type):
                        initialized_brokers.append(broker_type)
                        self.logger.info(f"Successfully initialized {broker_type.value}")
                    else:
                        self.logger.error(f"Failed to initialize {broker_type.value}")
                        success = False
                        
                except Exception as e:
                    self.logger.error(f"Error initializing {broker_type.value}: {e}")
                    success = False
            
            if initialized_brokers:
                # Initialize default routing rules if none provided
                if not self.config.routing_rules:
                    self._initialize_default_routing_rules()
                
                # Start health monitoring
                asyncio.create_task(self._health_monitor_loop())
                
                self.logger.info(f"Multi-broker system initialized with {len(initialized_brokers)} brokers")
                return True
            else:
                self.logger.error("No brokers were successfully initialized")
                return False
                
        except Exception as e:
            self.logger.error(f"Error initializing multi-broker system: {e}")
            return False
    
    async def _initialize_broker(self, broker_type: BrokerType) -> bool:
        """Initialize a specific broker"""
        try:
            broker = None
            
            if broker_type == BrokerType.ALPACA and self.config.alpaca_config:
                broker = AlpacaBroker(self.config.alpaca_config, self.event_manager)
                await broker.connect()
                self.broker_capabilities[broker_type] = BrokerCapability(
                    broker_type=broker_type,
                    asset_classes=[AssetClass.STOCK, AssetClass.ETF],
                    order_types=[OrderType.MARKET, OrderType.LIMIT, OrderType.STOP, OrderType.STOP_LIMIT],
                    time_in_force=["DAY", "GTC"],
                    max_position_size=1000000.0,
                    min_order_size=1.0,
                    max_order_size=100000.0,
                    supported_symbols=[],  # Would populate from broker
                    market_hours={"MONDAY": "09:30-16:00", "TUESDAY": "09:30-16:00", "WEDNESDAY": "09:30-16:00", "THURSDAY": "09:30-16:00", "FRIDAY": "09:30-16:00"},
                    commission_rate=0.0,
                    latency_ms=50,
                    reliability_score=0.95
                )
                
            elif broker_type == BrokerType.PAPER and self.config.paper_config:
                broker = PaperBroker(self.config.paper_config, self.event_manager)
                await broker.connect()
                self.broker_capabilities[broker_type] = BrokerCapability(
                    broker_type=broker_type,
                    asset_classes=[AssetClass.STOCK, AssetType.ETF],
                    order_types=[OrderType.MARKET, OrderType.LIMIT, OrderType.STOP, OrderType.STOP_LIMIT],
                    time_in_force=["DAY", "GTC"],
                    max_position_size=10000000.0,
                    min_order_size=1.0,
                    max_order_size=1000000.0,
                    supported_symbols=[],
                    market_hours={"MONDAY": "00:00-23:59", "TUESDAY": "00:00-23:59", "WEDNESDAY": "00:00-23:59", "THURSDAY": "00:00-23:59", "FRIDAY": "00:00-23:59"},
                    commission_rate=0.0,
                    latency_ms=10,
                    reliability_score=1.0
                )
                
            elif broker_type == BrokerType.IBKR and self.config.ibkr_config:
                broker = IBKRBroker(self.config.ibkr_config, self.event_manager)
                await broker.connect()
                self.broker_capabilities[broker_type] = BrokerCapability(
                    broker_type=broker_type,
                    asset_classes=[AssetClass.STOCK, AssetClass.OPTION, AssetClass.FUTURE, AssetClass.FOREX, AssetClass.CRYPTO],
                    order_types=[OrderType.MARKET, OrderType.LIMIT, OrderType.STOP, OrderType.STOP_LIMIT],
                    time_in_force=["DAY", "GTC", "IOC", "FOK"],
                    max_position_size=10000000.0,
                    min_order_size=1.0,
                    max_order_size=1000000.0,
                    supported_symbols=[],
                    market_hours={"MONDAY": "04:00-20:00", "TUESDAY": "04:00-20:00", "WEDNESDAY": "04:00-20:00", "THURSDAY": "04:00-20:00", "FRIDAY": "04:00-20:00"},
                    commission_rate=0.005,
                    latency_ms=100,
                    reliability_score=0.90
                )
                
            elif broker_type == BrokerType.BINANCE and self.config.binance_config:
                broker = BinanceBroker(self.config.binance_config, self.event_manager)
                await broker.connect()
                self.broker_capabilities[broker_type] = BrokerCapability(
                    broker_type=broker_type,
                    asset_classes=[AssetClass.CRYPTO],
                    order_types=[OrderType.MARKET, OrderType.LIMIT, OrderType.STOP, OrderType.STOP_LIMIT],
                    time_in_force=["GTC", "IOC", "FOK"],
                    max_position_size=1000000.0,
                    min_order_size=0.001,
                    max_order_size=100000.0,
                    supported_symbols=[],
                    market_hours={"MONDAY": "00:00-23:59", "TUESDAY": "00:00-23:59", "WEDNESDAY": "00:00-23:59", "THURSDAY": "00:00-23:59", "FRIDAY": "00:00-23:59"},
                    commission_rate=0.001,
                    latency_ms=30,
                    reliability_score=0.92
                )
                
            elif broker_type == BrokerType.COINBASE and self.config.coinbase_config:
                broker = CoinbaseBroker(self.config.coinbase_config, self.event_manager)
                await broker.connect()
                self.broker_capabilities[broker_type] = BrokerCapability(
                    broker_type=broker_type,
                    asset_classes=[AssetClass.CRYPTO],
                    order_types=[OrderType.MARKET, OrderType.LIMIT, OrderType.STOP, OrderType.STOP_LIMIT],
                    time_in_force=["GTC", "IOC", "FOK"],
                    max_position_size=500000.0,
                    min_order_size=0.001,
                    max_order_size=50000.0,
                    supported_symbols=[],
                    market_hours={"MONDAY": "00:00-23:59", "TUESDAY": "00:00-23:59", "WEDNESDAY": "00:00-23:59", "THURSDAY": "00:00-23:59", "FRIDAY": "00:00-23:59"},
                    commission_rate=0.005,
                    latency_ms=50,
                    reliability_score=0.88
                )
            
            if broker:
                self.brokers[broker_type] = broker
                
                # Initialize health status
                self.broker_health[broker_type] = BrokerHealthStatus(
                    broker_type=broker_type,
                    connected=True,
                    last_heartbeat=datetime.now(),
                    latency_ms=self.broker_capabilities[broker_type].latency_ms,
                    error_rate=0.0,
                    orders_today=0,
                    last_error=None,
                    reliability_score=self.broker_capabilities[broker_type].reliability_score
                )
                
                return True
            else:
                self.logger.warning(f"No configuration found for {broker_type.value}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error initializing {broker_type.value}: {e}")
            return False
    
    def _initialize_default_routing_rules(self):
        """Initialize default routing rules"""
        # Crypto routing - prefer Binance, fallback to Coinbase
        crypto_rule = RoutingRule(
            name="Crypto Default",
            asset_class=AssetClass.CRYPTO,
            symbol_patterns=["*"],
            preferred_brokers=[BrokerType.BINANCE, BrokerType.COINBASE],
            strategy=RoutingStrategy.BEST_PRICE,
            max_latency_ms=1000,
            min_reliability_score=0.8
        )
        
        # Stocks routing - prefer Alpaca, fallback to IBKR
        stock_rule = RoutingRule(
            name="Stocks Default",
            asset_class=AssetClass.STOCK,
            symbol_patterns=["*"],
            preferred_brokers=[BrokerType.ALPACA, BrokerType.IBKR],
            strategy=RoutingStrategy.LEAST_LOAD,
            max_latency_ms=500,
            min_reliability_score=0.9
        )
        
        # Paper trading for testing
        paper_rule = RoutingRule(
            name="Paper Trading",
            asset_class=AssetClass.STOCK,
            symbol_patterns=["TEST*", "PAPER*"],
            preferred_brokers=[BrokerType.PAPER],
            strategy=RoutingStrategy.PREFERRED,
            max_latency_ms=100,
            min_reliability_score=1.0
        )
        
        self.config.routing_rules = [crypto_rule, stock_rule, paper_rule]
    
    async def place_order(self, order_request: OrderRequest) -> OrderResult:
        """
        Place an order with intelligent routing
        
        Args:
            order_request: Order request to place
            
        Returns:
            OrderResult: Order placement result
        """
        try:
            self.logger.info(f"Multi-broker order: {order_request.symbol} {order_request.side} {order_request.quantity}")
            
            # Check daily order limit
            if self.daily_order_count >= self.config.max_daily_orders:
                return OrderResult(
                    success=False,
                    error_message="Daily order limit exceeded"
                )
            
            # Determine broker for routing
            selected_broker = await self._select_broker_for_order(order_request)
            
            if not selected_broker:
                return OrderResult(
                    success=False,
                    error_message="No suitable broker found for order"
                )
            
            # Place order with selected broker
            broker = self.brokers[selected_broker]
            result = await broker.place_order(order_request)
            
            # Update tracking
            if result and result.success:
                self.daily_order_count += 1
                self.broker_health[selected_broker].orders_today += 1
                self.last_routing_time[selected_broker] = datetime.now()
                
                # Log routing decision
                routing_decision = {
                    "timestamp": datetime.now(),
                    "order_id": result.order_id,
                    "symbol": order_request.symbol,
                    "broker": selected_broker.value,
                    "strategy": self.config.routing_strategy.value,
                    "success": True
                }
                self.routing_decisions.append(routing_decision)
                
                # Keep only recent decisions
                if len(self.routing_decisions) > 1000:
                    self.routing_decisions = self.routing_decisions[-500:]
                
                self.logger.info(f"Order routed to {selected_broker.value}: {result.order_id}")
            else:
                # Log failed routing decision
                routing_decision = {
                    "timestamp": datetime.now(),
                    "symbol": order_request.symbol,
                    "broker": selected_broker.value if selected_broker else "NONE",
                    "strategy": self.config.routing_strategy.value,
                    "success": False,
                    "error": result.error_message if result else "Unknown error"
                }
                self.routing_decisions.append(routing_decision)
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error in multi-broker order placement: {e}")
            return OrderResult(
                success=False,
                error_message=f"Multi-broker order failed: {e}"
            )
    
    async def cancel_order(self, broker_type: BrokerType, order_id: str) -> bool:
        """
        Cancel an order on specified broker
        
        Args:
            broker_type: Broker where order was placed
            order_id: Order ID to cancel
            
        Returns:
            bool: True if cancellation successful
        """
        try:
            if broker_type not in self.brokers:
                self.logger.error(f"Broker {broker_type.value} not available")
                return False
            
            broker = self.brokers[broker_type]
            return await broker.cancel_order(order_id)
            
        except Exception as e:
            self.logger.error(f"Error cancelling order on {broker_type.value}: {e}")
            return False
    
    async def get_positions(self) -> List[Position]:
        """
        Get consolidated positions across all brokers
        
        Returns:
            List[Position]: Consolidated positions
        """
        try:
            all_positions = []
            
            # Get positions from each broker
            for broker_type, broker in self.brokers.items():
                try:
                    positions = await broker.get_positions()
                    # Add broker info to positions
                    for position in positions:
                        position.broker = broker_type.value
                        all_positions.append(position)
                except Exception as e:
                    self.logger.error(f"Error getting positions from {broker_type.value}: {e}")
            
            # Consolidate positions by symbol
            consolidated_positions = self._consolidate_positions(all_positions)
            
            # Update cross-broker portfolio
            self.cross_broker_portfolio.clear()
            for position in consolidated_positions:
                self.cross_broker_portfolio[position.symbol] = position
            
            return consolidated_positions
            
        except Exception as e:
            self.logger.error(f"Error getting consolidated positions: {e}")
            return []
    
    async def get_account_info(self) -> Optional[AccountInfo]:
        """
        Get consolidated account information
        
        Returns:
            AccountInfo: Consolidated account info
        """
        try:
            total_cash = 0.0
            total_value = 0.0
            broker_count = 0
            
            # Get account info from each broker
            for broker_type, broker in self.brokers.items():
                try:
                    account_info = await broker.get_account_info()
                    if account_info:
                        total_cash += account_info.cash_balance
                        total_value += account_info.total_value
                        broker_count += 1
                except Exception as e:
                    self.logger.error(f"Error getting account info from {broker_type.value}: {e}")
            
            if broker_count > 0:
                return AccountInfo(
                    account_id="MULTI_BROKER_CONSOLIDATED",
                    broker="MULTI_BROKER",
                    currency="USD",
                    cash_balance=total_cash,
                    buying_power=total_value * 4,  # Assuming 4x leverage typical
                    total_value=total_value,
                    day_trade_count=0,
                    maintenance_margin=0.0,
                    equity_with_loan=total_value,
                    last_updated=datetime.now()
                )
            else:
                return None
                
        except Exception as e:
            self.logger.error(f"Error getting consolidated account info: {e}")
            return None
    
    async def subscribe_market_data(self, symbols: List[str]) -> bool:
        """
        Subscribe to market data across all brokers
        
        Args:
            symbols: List of symbols to subscribe to
            
        Returns:
            bool: True if subscription successful
        """
        try:
            success = True
            
            # Subscribe on each broker
            for broker_type, broker in self.brokers.items():
                try:
                    result = await broker.subscribe_market_data(symbols)
                    if not result:
                        self.logger.warning(f"Failed to subscribe to {broker_type.value}")
                        success = False
                except Exception as e:
                    self.logger.error(f"Error subscribing to {broker_type.value}: {e}")
                    success = False
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error in multi-broker market data subscription: {e}")
            return False
    
    async def get_best_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get best price across all brokers for a symbol
        
        Args:
            symbol: Symbol to get price for
            
        Returns:
            Dict[str, Any]: Best price information
        """
        try:
            best_price = None
            best_broker = None
            best_spread = float('inf')
            
            # Check each broker for the symbol
            for broker_type, broker in self.brokers.items():
                try:
                    if symbol in broker.market_data_cache:
                        data = broker.market_data_cache[symbol]
                        if data.bid > 0 and data.ask > 0:
                            spread = data.ask - data.bid
                            # Prefer tighter spreads
                            if spread < best_spread:
                                best_price = (data.bid + data.ask) / 2
                                best_broker = broker_type
                                best_spread = spread
                except Exception as e:
                    self.logger.error(f"Error getting price from {broker_type.value}: {e}")
                    continue
            
            if best_price and best_broker:
                return {
                    "symbol": symbol,
                    "best_price": best_price,
                    "best_broker": best_broker.value,
                    "spread": best_spread,
                    "timestamp": datetime.now()
                }
            else:
                return None
                
        except Exception as e:
            self.logger.error(f"Error getting best price for {symbol}: {e}")
            return None
    
    async def _select_broker_for_order(self, order_request: OrderRequest) -> Optional[BrokerType]:
        """Select best broker for an order"""
        try:
            # Determine asset class
            asset_class = self._determine_asset_class(order_request.symbol)
            
            # Apply routing rules
            for rule in self.config.routing_rules:
                if rule.enabled and self._matches_routing_rule(order_request, rule, asset_class):
                    # Test each preferred broker
                    for broker_type in rule.preferred_brokers:
                        if await self._is_broker_suitable(broker_type, order_request, rule):
                            return broker_type
            
            # Fallback to strategy-based selection
            return await self._select_broker_by_strategy(order_request, asset_class)
            
        except Exception as e:
            self.logger.error(f"Error selecting broker for order: {e}")
            return None
    
    def _determine_asset_class(self, symbol: str) -> AssetClass:
        """Determine asset class from symbol"""
        symbol_upper = symbol.upper()
        
        # Crypto detection
        crypto_symbols = ['BTC', 'ETH', 'LTC', 'XRP', 'ADA', 'DOT', 'USDT', 'USDC']
        if any(crypto in symbol_upper for crypto in crypto_symbols) or '_' in symbol:
            return AssetClass.CRYPTO
        
        # Options detection
        if len(symbol_upper) > 4 and any(c in symbol_upper for c in ['C', 'P']):
            return AssetClass.OPTION
        
        # Futures detection
        futures_symbols = ['ES', 'NQ', 'YM', 'RTY', 'CL', 'GC', 'SI']
        if any(future in symbol_upper for future in futures_symbols):
            return AssetClass.FUTURE
        
        # Forex detection (simplified)
        if any(pair in symbol_upper for pair in ['USD', 'EUR', 'GBP', 'JPY', 'CHF']):
            return AssetClass.FOREX
        
        # Default to stocks
        return AssetClass.STOCK
    
    def _matches_routing_rule(self, order_request: OrderRequest, rule: RoutingRule, asset_class: AssetClass) -> bool:
        """Check if order matches routing rule"""
        try:
            # Check asset class
            if rule.asset_class != asset_class:
                return False
            
            # Check symbol patterns
            symbol_matches = any(
                self._pattern_matches(order_request.symbol, pattern)
                for pattern in rule.symbol_patterns
            )
            
            if not symbol_matches:
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error checking routing rule match: {e}")
            return False
    
    def _pattern_matches(self, symbol: str, pattern: str) -> bool:
        """Check if symbol matches pattern (supports wildcards)"""
        try:
            import fnmatch
            return fnmatch.fnmatch(symbol.upper(), pattern.upper())
        except Exception:
            return symbol.upper() == pattern.upper()
    
    async def _is_broker_suitable(self, broker_type: BrokerType, order_request: OrderRequest, rule: RoutingRule) -> bool:
        """Check if broker is suitable for the order"""
        try:
            if broker_type not in self.brokers:
                return False
            
            broker = self.brokers[broker_type]
            capability = self.broker_capabilities[broker_type]
            health = self.broker_health[broker_type]
            
            # Check connection
            if not broker.is_connected():
                return False
            
            # Check health status
            if not health.is_healthy():
                return False
            
            # Check latency
            if health.latency_ms > rule.max_latency_ms:
                return False
            
            # Check reliability
            if health.reliability_score < rule.min_reliability_score:
                return False
            
            # Check order type support
            if order_request.order_type not in capability.order_types:
                return False
            
            # Check position size limits
            if order_request.quantity > capability.max_order_size:
                return False
            
            if order_request.quantity < capability.min_order_size:
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error checking broker suitability: {e}")
            return False
    
    async def _select_broker_by_strategy(self, order_request: OrderRequest, asset_class: AssetClass) -> Optional[BrokerType]:
        """Select broker based on routing strategy"""
        try:
            suitable_brokers = []
            
            # Get all suitable brokers
            for broker_type in self.brokers.keys():
                capability = self.broker_capabilities[broker_type]
                if asset_class in capability.asset_classes:
                    suitable_brokers.append(broker_type)
            
            if not suitable_brokers:
                return None
            
            # Apply strategy
            if self.config.routing_strategy == RoutingStrategy.ROUND_ROBIN:
                return self._select_round_robin(suitable_brokers)
            elif self.config.routing_strategy == RoutingStrategy.BEST_PRICE:
                return await self._select_best_price(suitable_brokers, order_request.symbol)
            elif self.config.routing_strategy == RoutingStrategy.LEAST_LOAD:
                return self._select_least_loaded(suitable_brokers)
            elif self.config.routing_strategy == RoutingStrategy.PREFERRED:
                return self._select_preferred(suitable_brokers, asset_class)
            else:
                # Default to first suitable broker
                return suitable_brokers[0]
                
        except Exception as e:
            self.logger.error(f"Error in strategy-based broker selection: {e}")
            return None
    
    def _select_round_robin(self, brokers: List[BrokerType]) -> BrokerType:
        """Select broker using round-robin strategy"""
        current_time = datetime.now()
        
        # Find broker with oldest last use
        oldest_broker = brokers[0]
        oldest_time = self.last_routing_time.get(oldest_broker, datetime.min)
        
        for broker in brokers:
            last_time = self.last_routing_time.get(broker, datetime.min)
            if last_time < oldest_time:
                oldest_broker = broker
                oldest_time = last_time
        
        return oldest_broker
    
    async def _select_best_price(self, brokers: List[BrokerType], symbol: str) -> Optional[BrokerType]:
        """Select broker with best price"""
        best_broker = None
        best_price = None
        best_spread = float('inf')
        
        for broker_type in brokers:
            broker = self.brokers[broker_type]
            try:
                if symbol in broker.market_data_cache:
                    data = broker.market_data_cache[symbol]
                    if data.bid > 0 and data.ask > 0:
                        spread = data.ask - data.bid
                        if spread < best_spread:
                            best_broker = broker_type
                            best_price = (data.bid + data.ask) / 2
                            best_spread = spread
            except Exception:
                continue
        
        return best_broker
    
    def _select_least_loaded(self, brokers: List[BrokerType]) -> BrokerType:
        """Select broker with least load"""
        least_loaded_broker = brokers[0]
        min_orders = self.broker_health[least_loaded_broker].orders_today
        
        for broker in brokers:
            orders_today = self.broker_health[broker].orders_today
            if orders_today < min_orders:
                least_loaded_broker = broker
                min_orders = orders_today
        
        return least_loaded_broker
    
    def _select_preferred(self, brokers: List[BrokerType], asset_class: AssetClass) -> Optional[BrokerType]:
        """Select preferred broker for asset class"""
        # Check if we have a primary broker for this asset class
        if asset_class in self.config.primary_brokers:
            primary_broker = self.config.primary_brokers[asset_class]
            if primary_broker in brokers:
                return primary_broker
        
        # Otherwise, return first broker in preferred list
        return brokers[0] if brokers else None
    
    def _consolidate_positions(self, positions: List[Position]) -> List[Position]:
        """Consolidate positions by symbol"""
        consolidated = {}
        
        for position in positions:
            symbol = position.symbol
            if symbol not in consolidated:
                consolidated[symbol] = Position(
                    symbol=symbol,
                    quantity=0.0,
                    avg_price=0.0,
                    market_value=0.0,
                    unrealized_pnl=0.0,
                    realized_pnl=0.0,
                    asset_type=position.asset_type,
                    broker="CONSOLIDATED",
                    last_updated=datetime.now()
                )
            
            # Accumulate quantities and calculate weighted average price
            existing = consolidated[symbol]
            total_quantity = existing.quantity + position.quantity
            
            if total_quantity > 0:
                existing.avg_price = (
                    existing.avg_price * existing.quantity + 
                    position.avg_price * position.quantity
                ) / total_quantity
                existing.quantity = total_quantity
                existing.unrealized_pnl += position.unrealized_pnl
                existing.realized_pnl += position.realized_pnl
        
        return list(consolidated.values())
    
    async def _health_monitor_loop(self):
        """Monitor broker health"""
        while not self._shutdown_event.is_set():
            try:
                for broker_type, broker in self.brokers.items():
                    try:
                        # Check connection
                        is_connected = broker.is_connected()
                        
                        # Update health status
                        health = self.broker_health[broker_type]
                        health.connected = is_connected
                        health.last_heartbeat = datetime.now()
                        
                        # Test latency (simplified)
                        start_time = time.time()
                        # Would perform actual latency test here
                        health.latency_ms = (time.time() - start_time) * 1000
                        
                        # Update reliability score based on recent performance
                        # This would be more sophisticated in production
                        
                    except Exception as e:
                        health = self.broker_health[broker_type]
                        health.connected = False
                        health.last_error = str(e)
                
                await asyncio.sleep(self.config.health_check_interval)
                
            except Exception as e:
                self.logger.error(f"Error in health monitor: {e}")
                await asyncio.sleep(60)  # Wait longer on error
    
    def get_routing_decisions(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent routing decisions"""
        return self.routing_decisions[-limit:]
    
    def get_broker_status(self) -> Dict[str, Any]:
        """Get status of all brokers"""
        status = {}
        
        for broker_type, health in self.broker_health.items():
            status[broker_type.value] = {
                "connected": health.connected,
                "healthy": health.is_healthy(),
                "latency_ms": health.latency_ms,
                "error_rate": health.error_rate,
                "orders_today": health.orders_today,
                "reliability_score": health.reliability_score,
                "last_heartbeat": health.last_heartbeat.isoformat() if health.last_heartbeat else None,
                "last_error": health.last_error
            }
        
        return status
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics"""
        return {
            "total_brokers": len(self.brokers),
            "healthy_brokers": sum(1 for health in self.broker_health.values() if health.is_healthy()),
            "daily_orders": self.daily_order_count,
            "consolidated_positions": len(self.cross_broker_portfolio),
            "routing_decisions_count": len(self.routing_decisions),
            "broker_status": self.get_broker_status(),
            "routing_strategy": self.config.routing_strategy.value,
            "enabled_brokers": [b.value for b in self.config.enabled_brokers]
        }
    
    async def close(self):
        """Close all broker connections"""
        try:
            self.logger.info("Closing multi-broker system")
            
            self._shutdown_event.set()
            
            # Close each broker
            for broker_type, broker in self.brokers.items():
                try:
                    await broker.disconnect()
                except Exception as e:
                    self.logger.error(f"Error closing {broker_type.value}: {e}")
            
            self.logger.info("Multi-broker system closed")
            
        except Exception as e:
            self.logger.error(f"Error closing multi-broker system: {e}")