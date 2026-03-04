"""
Core data types for the trading system

This module provides fundamental data types used throughout the trading system.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
import uuid


@dataclass
class OrderRequest:
    """Request to place an order"""
    symbol: str
    side: str  # "buy" or "sell"
    quantity: float
    order_type: str  # "market", "limit", "stop", "stop_limit"
    order_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    price: Optional[float] = None  # For limit orders
    stop_price: Optional[float] = None  # For stop orders
    time_in_force: str = "day"  # "day", "gtc", "ioc", "fok"
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate order request"""
        if self.quantity <= 0:
            raise ValueError("Quantity must be positive")
        if self.order_type == "limit" and self.price is None:
            raise ValueError("Limit price required for limit orders")
        if self.order_type == "stop" and self.stop_price is None:
            raise ValueError("Stop price required for stop orders")


@dataclass
class PositionRequest:
    """Request for position information or modification"""
    symbol: str
    action: str = "get"  # "get", "close", "modify"
    quantity: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AccountRequest:
    """Request for account information or modification"""
    account_id: Optional[str] = None
    action: str = "get"  # "get", "update", "close"
    metadata: Dict[str, Any] = field(default_factory=dict)
