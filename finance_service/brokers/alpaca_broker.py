"""
Alpaca Broker Integration for Live Trading.

Alpaca is a commission-free trading platform with REST API.
This module provides integration with Alpaca for:
- Live order placement and management
- Real-time account and position information
- Market data access
"""

import logging
import requests
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from .base_broker import (
    BaseBroker, OrderRequest, Order, OrderStatus, OrderSide, OrderType,
    Position, Account
)

logger = logging.getLogger(__name__)


@dataclass
class AlpacaConfig:
    """Configuration for Alpaca broker."""
    api_key: str
    api_secret: str
    base_url: str = "https://paper-api.alpaca.markets"
    timeout: float = 10.0


class AlpacaBroker(BaseBroker):
    """
    Alpaca broker integration for live trading.
    
    Requires:
    - APCA_API_BASE_URL environment variable (paper or live)
    - APCA_API_KEY_ID environment variable
    - APCA_API_SECRET_KEY environment variable
    """
    
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        base_url: str = "https://paper-api.alpaca.markets",  # Paper trading by default
        timeout: float = 10.0,
    ):
        """
        Initialize Alpaca broker.
        
        Args:
            api_key: Alpaca API key
            api_secret: Alpaca API secret
            base_url: API base URL (paper or live)
            timeout: Request timeout in seconds
        """
        is_paper = "paper" in base_url.lower()
        super().__init__("Alpaca", paper_trading=is_paper)
        
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url
        self.timeout = timeout
        
        self.headers = {
            "APCA-API-KEY-ID": api_key,
        }
        
        logger.info(f"AlpacaBroker initialized (paper_trading={is_paper})")
    
    def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """
        Make HTTP request to Alpaca API.
        
        Args:
            method: HTTP method (GET, POST, DELETE, etc.)
            endpoint: API endpoint path
            **kwargs: Additional arguments for requests
            
        Returns:
            Response JSON
        """
        url = f"{self.base_url}{endpoint}"
        kwargs["headers"] = self.headers
        kwargs["timeout"] = self.timeout
        
        response = requests.request(method, url, **kwargs)
        response.raise_for_status()
        
        return response.json()
    
    # =====================
    # ACCOUNT OPERATIONS
    # =====================
    
    def get_account(self) -> Account:
        """Get account information from Alpaca"""
        data = self._request("GET", "/v2/account")
        
        return Account(
            account_number=data.get("account_number", "UNKNOWN"),
            cash=float(data.get("cash", 0)),
            buying_power=float(data.get("buying_power", 0)),
            total_equity=float(data.get("equity", 0)),
            initial_equity=float(data.get("equity", 0)),
            net_value=float(data.get("net_liquidation_value", 0)),
            multiplier=4.0 if data.get("account_type") == "margin" else 1.0,
            is_margin=data.get("account_type") == "margin",
            can_daytrade=data.get("day_trading_buying_power") is not None,
            last_updated=datetime.now(),
        )
    
    def get_cash(self) -> float:
        """Get available cash"""
        return self.get_account().cash
    
    def get_buying_power(self) -> float:
        """Get available buying power"""
        return self.get_account().buying_power
    
    def get_account_value(self) -> float:
        """Get total account value"""
        return self.get_account().total_equity
    
    # =====================
    # POSITION OPERATIONS
    # =====================
    
    def get_positions(self) -> Dict[str, Position]:
        """Get all open positions"""
        positions_data = self._request("GET", "/v2/positions")
        positions = {}
        
        for pos_data in positions_data:
            symbol = pos_data["symbol"]
            quantity = float(pos_data["qty"])
            entry_price = float(pos_data["avg_fill_price"])
            current_price = float(pos_data["current_price"])
            
            positions[symbol] = Position(
                symbol=symbol,
                quantity=quantity,
                entry_price=entry_price,
                current_price=current_price,
                market_value=float(pos_data["market_value"]),
                unrealized_pnl=float(pos_data["unrealized_pl"]),
                unrealized_pnl_pct=float(pos_data["unrealized_plpc"]) * 100,
                side="long" if quantity > 0 else "short",
            )
        
        return positions
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for specific symbol"""
        try:
            pos_data = self._request("GET", f"/v2/positions/{symbol}")
            quantity = float(pos_data["qty"])
            entry_price = float(pos_data["avg_fill_price"])
            current_price = float(pos_data["current_price"])
            
            return Position(
                symbol=symbol,
                quantity=quantity,
                entry_price=entry_price,
                current_price=current_price,
                market_value=float(pos_data["market_value"]),
                unrealized_pnl=float(pos_data["unrealized_pl"]),
                unrealized_pnl_pct=float(pos_data["unrealized_plpc"]) * 100,
                side="long" if quantity > 0 else "short",
            )
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                return None
            raise
    
    def close_position(self, symbol: str) -> Order:
        """Close entire position at market"""
        response = self._request("DELETE", f"/v2/positions/{symbol}")
        return self._parse_order(response)
    
    # =====================
    # ORDER OPERATIONS
    # =====================
    
    def place_order(self, order_request: OrderRequest) -> Order:
        """Place an order"""
        data = {
            "symbol": order_request.symbol,
            "qty": order_request.quantity,
            "side": order_request.side.value,
            "type": order_request.order_type.value,
            "time_in_force": order_request.time_in_force,
        }
        
        if order_request.price is not None:
            data["limit_price"] = order_request.price
        
        if order_request.stop_price is not None:
            data["stop_price"] = order_request.stop_price
        
        response = self._request("POST", "/v2/orders", json=data)
        return self._parse_order(response)
    
    def get_order(self, order_id: str) -> Optional[Order]:
        """Get order by ID"""
        try:
            data = self._request("GET", f"/v2/orders/{order_id}")
            return self._parse_order(data)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                return None
            raise
    
    def get_orders(self, status: Optional[OrderStatus] = None) -> List[Order]:
        """Get orders, optionally filtered by status"""
        params = {}
        if status:
            params["status"] = status.value
        
        data = self._request("GET", "/v2/orders", params=params)
        return [self._parse_order(order_data) for order_data in data]
    
    def cancel_order(self, order_id: str) -> Order:
        """Cancel an order"""
        self._request("DELETE", f"/v2/orders/{order_id}")
        # Return updated order
        return self.get_order(order_id)
    
    # =====================
    # MARKET DATA
    # =====================
    
    def get_last_quote(self, symbol: str) -> Dict[str, float]:
        """Get last quote for a symbol"""
        try:
            data = self._request("GET", f"/v2/last/quotes", params={"symbols": symbol})
            quote = data["quotes"][symbol]
            
            return {
                "bid": float(quote["bp"]),
                "ask": float(quote["ap"]),
                "last": (float(quote["bp"]) + float(quote["ap"])) / 2,
                "bid_size": int(quote["bs"]),
                "ask_size": int(quote["as"]),
            }
        except Exception as e:
            logger.warning(f"Failed to get quote for {symbol}: {e}")
            return {
                "bid": 0.0,
                "ask": 0.0,
                "last": 0.0,
                "bid_size": 0,
                "ask_size": 0,
            }
    
    # =====================
    # UTILITY METHODS
    # =====================
    
    def is_market_open(self) -> bool:
        """Check if market is currently open"""
        try:
            data = self._request("GET", "/v2/clock")
            return data["is_open"]
        except Exception as e:
            logger.warning(f"Failed to check market status: {e}")
            return super().is_market_open()
    
    # =====================
    # INTERNAL METHODS
    # =====================
    
    def _parse_order(self, data: Dict[str, Any]) -> Order:
        """Parse Alpaca order response into Order object"""
        status_map = {
            "new": OrderStatus.SUBMITTED,
            "partially_filled": OrderStatus.PARTIAL,
            "filled": OrderStatus.FILLED,
            "done_for_day": OrderStatus.CANCELLED,
            "cancelled": OrderStatus.CANCELLED,
            "expired": OrderStatus.EXPIRED,
            "pending_new": OrderStatus.PENDING,
            "pending_cancel": OrderStatus.PENDING,
            "pending_replace": OrderStatus.PENDING,
            "rejected": OrderStatus.REJECTED,
            "suspended": OrderStatus.CANCELLED,
            "accepted": OrderStatus.ACCEPTED,
            "accepted_for_bidding": OrderStatus.ACCEPTED,
            "stopped": OrderStatus.CANCELLED,
        }
        
        side_map = {"buy": OrderSide.BUY, "sell": OrderSide.SELL}
        type_map = {
            "market": OrderType.MARKET,
            "limit": OrderType.LIMIT,
            "stop": OrderType.STOP,
            "stop_limit": OrderType.STOP_LIMIT,
        }
        
        return Order(
            order_id=data["id"],
            symbol=data["symbol"],
            side=side_map.get(data["side"], OrderSide.BUY),
            quantity=float(data["qty"]),
            filled_quantity=float(data.get("filled_qty", 0)),
            avg_fill_price=float(data.get("filled_avg_price", 0)),
            status=status_map.get(data["status"], OrderStatus.PENDING),
            order_type=type_map.get(data["order_type"], OrderType.MARKET),
            submitted_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")),
            filled_at=datetime.fromisoformat(data["filled_at"].replace("Z", "+00:00")) if data.get("filled_at") else None,
            cancelled_at=datetime.fromisoformat(data["cancelled_at"].replace("Z", "+00:00")) if data.get("cancelled_at") else None,
        )
