"""
Broker integrations for live trading.

Supported brokers:
- Paper Trading (simulated, for testing)
- Alpaca (commission-free trading)
- Interactive Brokers (IBKR) - professional trading
- TD Ameritrade (TDA) - retail trading
- Binance - cryptocurrency exchange
- Coinbase Pro - cryptocurrency exchange

Multi-Broker Features:
- Intelligent order routing across brokers
- Cross-broker portfolio consolidation
- Risk management and alerts
- Performance optimization and load balancing
- Broker failover and redundancy

Advanced Order Types:
- Trailing Stop Orders
- OCO (One Cancels Other) Orders
- Bracket Orders
- Iceberg Orders
"""

from .base_broker import (
    BaseBroker,
    OrderRequest,
    Order,
    OrderStatus,
    OrderSide,
    OrderType,
    Position,
    Account,
)
from .paper_broker import PaperBroker
from .alpaca_broker import AlpacaBroker
from .broker_manager import BrokerManager, BrokerMode

__all__ = [
    # Base classes & enums
    "BaseBroker",
    "OrderRequest",
    "Order",
    "OrderStatus",
    "OrderSide",
    "OrderType",
    "Position",
    "Account",
    
    # Broker implementations
    "PaperBroker",
    "AlpacaBroker",
    "BrokerManager",
    "BrokerMode",
]
