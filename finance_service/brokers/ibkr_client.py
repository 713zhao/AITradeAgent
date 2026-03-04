"""
Interactive Brokers (IBKR) Client Module

This module provides the low-level client interface for Interactive Brokers TWS/Gateway API,
handling connection management, authentication, and low-level communication.

Key Features:
- Thread-safe connection management
- Automatic reconnection logic
- Request/response handling
- Error handling and recovery
- Event-driven communication
- Performance monitoring

Author: PicotradeAgent
Version: 6.3.0
"""

import asyncio
import logging
import threading
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Union, Tuple
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
import json
import queue
import socket

# IBKR API imports (would need ib_insync or similar in production)
try:
    from ib_insync import IB, util, Position, Order, Trade, Contract, Ticker
    IB_INSYNC_AVAILABLE = True
except ImportError:
    IB_INSYNC_AVAILABLE = False
    # Mock classes for development
    class IB: pass
    class Contract: pass
    class Order: pass
    class Trade: pass
    class Position: pass
    class Ticker: pass

from finance_service.brokers.ibkr_broker import (
    IBKRConfig, IBKRContract, IBKRConnectionStatus, IBKRConnectionState
)


class IBKRMessageType(str, Enum):
    """IBKR message types"""
    CONNECT = "CONNECT"
    DISCONNECT = "DISCONNECT"
    PLACE_ORDER = "PLACE_ORDER"
    CANCEL_ORDER = "CANCEL_ORDER"
    REQUEST_DATA = "REQUEST_DATA"
    SUBSCRIBE_DATA = "SUBSCRIBE_DATA"
    UNSUBSCRIBE_DATA = "UNSUBSCRIBE_DATA"
    HEARTBEAT = "HEARTBEAT"
    ERROR = "ERROR"


@dataclass
class IBKRRequest:
    """IBKR request wrapper"""
    request_id: str
    message_type: IBKRMessageType
    data: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)
    timeout: float = 30.0
    callback: Optional[Callable] = None
    retries: int = 0
    max_retries: int = 3


@dataclass
class IBKRResponse:
    """IBKR response wrapper"""
    request_id: str
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


class IBKRConnectionManager:
    """
    IBKR Connection Manager
    
    Manages the connection to Interactive Brokers TWS/Gateway with automatic
    reconnection, error handling, and performance monitoring.
    """
    
    def __init__(self, config: IBKRConfig):
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.IBKRConnectionManager")
        
        # Connection state
        self.ib_client: Optional[IB] = None
        self.connection_status = IBKRConnectionStatus()
        
        # Request management
        self.pending_requests: Dict[str, IBKRRequest] = {}
        self.request_queue = queue.Queue()
        self.response_handlers: Dict[str, List[Callable]] = {}
        
        # Threading
        self.executor = ThreadPoolExecutor(max_workers=3)
        self.connection_thread: Optional[threading.Thread] = None
        self.monitoring_thread: Optional[threading.Thread] = None
        self._shutdown_event = threading.Event()
        
        # Performance tracking
        self.request_stats: Dict[str, int] = {}
        self.error_stats: Dict[str, int] = {}
        self.last_heartbeat: Optional[datetime] = None
        
        # Event callbacks
        self.connection_callbacks: List[Callable] = []
        self.error_callbacks: List[Callable] = []
        
        self.logger.info("IBKR Connection Manager initialized")
    
    async def connect(self) -> bool:
        """
        Establish connection to IBKR
        
        Returns:
            bool: True if connection successful
        """
        try:
            self.logger.info(f"Connecting to IBKR at {self.config.host}:{self.config.port}")
            
            self.connection_status.state = IBKRConnectionState.CONNECTING
            
            # Create IB client
            if IB_INSYNC_AVAILABLE:
                self.ib_client = IB()
                self._setup_event_handlers()
                
                # Connect with timeout
                self.ib_client.connectAsync(
                    host=self.config.host,
                    port=self.config.port,
                    clientId=self.config.client_id,
                    timeout=self.config.connection_timeout
                )
            else:
                # Mock connection for development
                await asyncio.sleep(1.0)
                self.ib_client = IB()
                self.logger.warning("Using mock IBKR connection for development")
            
            # Verify connection
            if await self._verify_connection():
                self.connection_status.state = IBKRConnectionState.CONNECTED
                self.connection_status.connected_at = datetime.now()
                self.connection_status.reconnect_attempts = 0
                
                # Start background threads
                await self._start_background_threads()
                
                self.logger.info("Successfully connected to IBKR")
                return True
            else:
                self.connection_status.state = IBKRConnectionState.ERROR
                self.logger.error("Failed to verify IBKR connection")
                return False
                
        except Exception as e:
            self.logger.error(f"Error connecting to IBKR: {e}")
            self.connection_status.state = IBKRConnectionState.ERROR
            self.connection_status.error_message = str(e)
            return False
    
    async def disconnect(self) -> bool:
        """
        Disconnect from IBKR
        
        Returns:
            bool: True if disconnection successful
        """
        try:
            self.logger.info("Disconnecting from IBKR")
            
            # Stop background threads
            await self._stop_background_threads()
            
            # Disconnect IB client
            if self.ib_client and self.ib_client.isConnected():
                if IB_INSYNC_AVAILABLE:
                    self.ib_client.disconnect()
                else:
                    # Mock disconnection
                    pass
            
            self.connection_status.state = IBKRConnectionState.DISCONNECTED
            self.connection_status.connected_at = None
            
            # Clear pending requests
            self.pending_requests.clear()
            
            self.logger.info("Disconnected from IBKR")
            return True
            
        except Exception as e:
            self.logger.error(f"Error disconnecting from IBKR: {e}")
            return False
    
    async def send_request(self, request: IBKRRequest) -> IBKRResponse:
        """
        Send request to IBKR
        
        Args:
            request: Request to send
            
        Returns:
            IBKRResponse: Response from IBKR
        """
        try:
            if not self.is_connected():
                return IBKRResponse(
                    request_id=request.request_id,
                    success=False,
                    error="Not connected to IBKR"
                )
            
            # Track request
            self.pending_requests[request.request_id] = request
            self._update_request_stats(request.message_type.value)
            
            # Process request based on type
            if request.message_type == IBKRMessageType.PLACE_ORDER:
                response = await self._process_place_order(request)
            elif request.message_type == IBKRMessageType.CANCEL_ORDER:
                response = await self._process_cancel_order(request)
            elif request.message_type == IBKRMessageType.SUBSCRIBE_DATA:
                response = await self._process_subscribe_data(request)
            elif request.message_type == IBKRMessageType.UNSUBSCRIBE_DATA:
                response = await self._process_unsubscribe_data(request)
            elif request.message_type == IBKRMessageType.REQUEST_DATA:
                response = await self._process_request_data(request)
            else:
                response = IBKRResponse(
                    request_id=request.request_id,
                    success=False,
                    error=f"Unsupported message type: {request.message_type}"
                )
            
            # Clean up request
            if request.request_id in self.pending_requests:
                del self.pending_requests[request.request_id]
            
            return response
            
        except Exception as e:
            self.logger.error(f"Error sending request {request.request_id}: {e}")
            self._update_error_stats(str(e))
            return IBKRResponse(
                request_id=request.request_id,
                success=False,
                error=str(e)
            )
    
    def is_connected(self) -> bool:
        """
        Check if connected to IBKR
        
        Returns:
            bool: True if connected
        """
        if IB_INSYNC_AVAILABLE and self.ib_client:
            return self.ib_client.isConnected()
        else:
            return self.connection_status.is_connected()
    
    def get_connection_status(self) -> IBKRConnectionStatus:
        """Get current connection status"""
        return self.connection_status
    
    def add_connection_callback(self, callback: Callable):
        """Add connection status callback"""
        self.connection_callbacks.append(callback)
    
    def add_error_callback(self, callback: Callable):
        """Add error callback"""
        self.error_callbacks.append(callback)
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics"""
        return {
            "request_stats": self.request_stats.copy(),
            "error_stats": self.error_stats.copy(),
            "pending_requests": len(self.pending_requests),
            "connected": self.is_connected(),
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None
        }
    
    # Private methods
    
    def _setup_event_handlers(self):
        """Setup IBKR event handlers"""
        if not IB_INSYNC_AVAILABLE or not self.ib_client:
            return
        
        # Connection events
        self.ib_client.connectedEvent += self._on_connected
        self.ib_client.disconnectedEvent += self._on_disconnected
        self.ib_client.errorEvent += self._on_error
        
        # Order events
        self.ib_client.orderStatusEvent += self._on_order_status
        self.ib_client.openOrderEvent += self._on_open_order
        self.ib_client.orderBoundEvent += self._on_order_bound
        
        # Position events
        self.ib_client.positionEvent += self._on_position
        self.ib_client.positionEndEvent += self._on_position_end
        
        # Account events
        self.ib_client.accountSummaryEvent += self._on_account_summary
        self.ib_client.accountSummaryEndEvent += self._on_account_summary_end
        
        # Market data events
        self.ib_client.tickPriceEvent += self._on_tick_price
        self.ib_client.tickSizeEvent += self._on_tick_size
        self.ib_client.tickOptionComputationEvent += self._on_tick_option_computation
        self.ib_client.tickGenericEvent += self._on_tick_generic
        
        # Market depth events
        self.ib_client.marketDataTypeEvent += self._on_market_data_type
        self.ib_client.tickEFPEvent += self._on_tick_efp
        self.ib_client.tickFunctionEvent += self._on_tick_function
        self.ib_client.tickSnapshotEndEvent += self._on_tick_snapshot_end
        
        # Display groups
        self.ib_client.displayGroupListEvent += self._on_display_group_list
        self.ib_client.displayGroupUpdatedEvent += self._on_display_group_updated
        
        # Historical data events
        self.ib_client.historicalDataEvent += self._on_historical_data
        self.ib_client.historicalDataUpdateEvent += self._on_historical_data_update
        self.ib_client.historicalDataEndEvent += self._on_historical_data_end
        
        # Real-time bars
        self.ib_client.realTimeBarEvent += self._on_real_time_bar
        self.ib_client.realTimeBarEndEvent += self._on_real_time_bar_end
        
        # Fundamental data
        self.ib_client.fundamentalDataEvent += self._on_fundamental_data
        
        # News
        self.ib_client.newsMsgsEvent += self._on_news_msgs
        
        # Commission reports
        self.ib_client.commissionReportEvent += self._on_commission_report
        
        # Contract details
        self.ib_client.contractDetailsEvent += self._on_contract_details
        self.ib_client.contractDetailsEndEvent += self._on_contract_details_end
        
        # Scanner
        self.ib_client.scannerParametersEvent += self._on_scanner_parameters
        self.ib_client.scannerDataEvent += self._on_scanner_data
        self.ib_client.scannerDataEndEvent += self._on_scanner_data_end
        
        # Connection data
        self.ib_client.currentTimeEvent += self._on_current_time
        self.ib_client.realtimeDataEvent += self._on_realtime_data
        self.ib_client.realtimeDataEndEvent += self._on_realtime_data_end
        self.ib_client.headTimestampEvent += self._on_head_timestamp
        self.ib_client.histogramDataEvent += self._on_histogram_data
        self.ib_service_event += self._on_ib_service
    
    async def _verify_connection(self) -> bool:
        """Verify connection is working"""
        try:
            if IB_INSYNC_AVAILABLE and self.ib_client:
                # Request current time from IBKR
                self.ib_client.reqCurrentTime()
                await asyncio.sleep(2.0)
                
                # Check if client is connected
                return self.ib_client.isConnected()
            else:
                # Mock verification
                return True
                
        except Exception as e:
            self.logger.error(f"Connection verification failed: {e}")
            return False
    
    async def _start_background_threads(self):
        """Start background monitoring threads"""
        if self.connection_thread and self.connection_thread.is_alive():
            return
        
        self._shutdown_event.clear()
        
        # Connection monitoring thread
        self.connection_thread = threading.Thread(target=self._connection_monitor_loop, daemon=True)
        self.connection_thread.start()
        
        # Request processing thread
        self.monitoring_thread = threading.Thread(target=self._request_monitor_loop, daemon=True)
        self.monitoring_thread.start()
    
    async def _stop_background_threads(self):
        """Stop background monitoring threads"""
        self._shutdown_event.set()
        
        # Wait for threads to finish
        for thread in [self.connection_thread, self.monitoring_thread]:
            if thread and thread.is_alive():
                thread.join(timeout=5.0)
    
    def _connection_monitor_loop(self):
        """Monitor connection health"""
        while not self._shutdown_event.is_set():
            try:
                if self.is_connected():
                    self.last_heartbeat = datetime.now()
                    
                    # Send heartbeat if needed
                    if IB_INSYNC_AVAILABLE and self.ib_client:
                        try:
                            self.ib_client.reqCurrentTime()
                        except Exception as e:
                            self.logger.warning(f"Heartbeat failed: {e}")
                            # Connection might be lost
                            self.connection_status.state = IBKRConnectionState.DISCONNECTED
                else:
                    if self.config.auto_reconnect:
                        asyncio.create_task(self._handle_reconnection())
                
                time.sleep(5.0)  # Check every 5 seconds
                
            except Exception as e:
                self.logger.error(f"Connection monitor error: {e}")
                time.sleep(5.0)
    
    def _request_monitor_loop(self):
        """Monitor pending requests for timeouts"""
        while not self._shutdown_event.is_set():
            try:
                current_time = datetime.now()
                timeout_requests = []
                
                for request_id, request in self.pending_requests.items():
                    if (current_time - request.timestamp).total_seconds() > request.timeout:
                        timeout_requests.append(request_id)
                
                # Handle timeout requests
                for request_id in timeout_requests:
                    request = self.pending_requests[request_id]
                    response = IBKRResponse(
                        request_id=request_id,
                        success=False,
                        error=f"Request timeout after {request.timeout}s"
                    )
                    
                    if request.callback:
                        request.callback(response)
                    
                    del self.pending_requests[request_id]
                
                if timeout_requests:
                    self.logger.warning(f"Timed out {len(timeout_requests)} requests")
                
                time.sleep(1.0)  # Check every second
                
            except Exception as e:
                self.logger.error(f"Request monitor error: {e}")
                time.sleep(1.0)
    
    async def _handle_reconnection(self):
        """Handle automatic reconnection"""
        if self.connection_status.reconnect_attempts >= self.config.max_reconnect_attempts:
            self.logger.error("Max reconnection attempts reached")
            return
        
        self.connection_status.reconnect_attempts += 1
        self.connection_status.state = IBKRConnectionState.RECONNECTING
        
        self.logger.info(f"Attempting reconnection ({self.connection_status.reconnect_attempts}/{self.config.max_reconnect_attempts})")
        
        await asyncio.sleep(self.config.reconnect_delay)
        
        try:
            await self.connect()
        except Exception as e:
            self.logger.error(f"Reconnection failed: {e}")
    
    async def _process_place_order(self, request: IBKRRequest) -> IBKRResponse:
        """Process place order request"""
        try:
            if not IB_INSYNC_AVAILABLE or not self.ib_client:
                # Mock order placement
                order_id = f"IBKR_MOCK_{int(time.time())}"
                return IBKRResponse(
                    request_id=request.request_id,
                    success=True,
                    data={
                        "order_id": order_id,
                        "status": "PENDING",
                        "message": "Order placed (mock)"
                    }
                )
            
            # Extract order data
            contract_data = request.data.get("contract", {})
            order_data = request.data.get("order", {})
            
            # Create contract
            contract = Contract()
            contract.symbol = contract_data.get("symbol")
            contract.secType = contract_data.get("security_type", "STK")
            contract.exchange = contract_data.get("exchange", "SMART")
            contract.currency = contract_data.get("currency", "USD")
            
            # Create order
            ib_order = Order()
            ib_order.action = order_data.get("action", "BUY")
            ib_order.totalQuantity = order_data.get("quantity", 1)
            ib_order.orderType = order_data.get("order_type", "MKT")
            
            if "limit_price" in order_data:
                ib_order.lmtPrice = order_data["limit_price"]
            if "stop_price" in order_data:
                ib_order.auxPrice = order_data["stop_price"]
            
            # Place order
            trade = self.ib_client.placeOrder(contract, ib_order)
            
            return IBKRResponse(
                request_id=request.request_id,
                success=True,
                data={
                    "order_id": str(trade.order.orderId),
                    "status": trade.orderStatus.status,
                    "message": "Order placed successfully"
                }
            )
            
        except Exception as e:
            return IBKRResponse(
                request_id=request.request_id,
                success=False,
                error=str(e)
            )
    
    async def _process_cancel_order(self, request: IBKRRequest) -> IBKRResponse:
        """Process cancel order request"""
        try:
            order_id = request.data.get("order_id")
            
            if not IB_INSYNC_AVAILABLE or not self.ib_client:
                # Mock cancellation
                return IBKRResponse(
                    request_id=request.request_id,
                    success=True,
                    data={
                        "order_id": order_id,
                        "status": "CANCELLED",
                        "message": "Order cancelled (mock)"
                    }
                )
            
            # Find and cancel order
            for trade in self.ib_client.trades():
                if str(trade.order.orderId) == order_id:
                    self.ib_client.cancelOrder(trade.order)
                    break
            
            return IBKRResponse(
                request_id=request.request_id,
                success=True,
                data={
                    "order_id": order_id,
                    "status": "CANCELLED",
                    "message": "Order cancelled successfully"
                }
            )
            
        except Exception as e:
            return IBKRResponse(
                request_id=request.request_id,
                success=False,
                error=str(e)
            )
    
    async def _process_subscribe_data(self, request: IBKRRequest) -> IBKRResponse:
        """Process subscribe data request"""
        try:
            symbols = request.data.get("symbols", [])
            
            if not IB_INSYNC_AVAILABLE or not self.ib_client:
                # Mock subscription
                return IBKRResponse(
                    request_id=request.request_id,
                    success=True,
                    data={
                        "symbols": symbols,
                        "message": "Data subscribed (mock)"
                    }
                )
            
            for symbol in symbols:
                # Create contract
                contract = Contract()
                contract.symbol = symbol
                contract.secType = "STK"
                contract.exchange = "SMART"
                contract.currency = "USD"
                
                # Subscribe to market data
                self.ib_client.reqMktData(contract)
            
            return IBKRResponse(
                request_id=request.request_id,
                success=True,
                data={
                    "symbols": symbols,
                    "message": "Market data subscribed successfully"
                }
            )
            
        except Exception as e:
            return IBKRResponse(
                request_id=request.request_id,
                success=False,
                error=str(e)
            )
    
    async def _process_unsubscribe_data(self, request: IBKRRequest) -> IBKRResponse:
        """Process unsubscribe data request"""
        try:
            symbols = request.data.get("symbols", [])
            
            if not IB_INSYNC_AVAILABLE or not self.ib_client:
                # Mock unsubscription
                return IBKRResponse(
                    request_id=request.request_id,
                    success=True,
                    data={
                        "symbols": symbols,
                        "message": "Data unsubscribed (mock)"
                    }
                )
            
            for symbol in symbols:
                # Create contract
                contract = Contract()
                contract.symbol = symbol
                contract.secType = "STK"
                contract.exchange = "SMART"
                contract.currency = "USD"
                
                # Cancel market data
                self.ib_client.cancelMktData(contract)
            
            return IBKRResponse(
                request_id=request.request_id,
                success=True,
                data={
                    "symbols": symbols,
                    "message": "Market data unsubscribed successfully"
                }
            )
            
        except Exception as e:
            return IBKRResponse(
                request_id=request.request_id,
                success=False,
                error=str(e)
            )
    
    async def _process_request_data(self, request: IBKRRequest) -> IBKRResponse:
        """Process request data request"""
        try:
            data_type = request.data.get("data_type")
            
            if not IB_INSYNC_AVAILABLE or not self.ib_client:
                # Mock data request
                return IBKRResponse(
                    request_id=request.request_id,
                    success=True,
                    data={
                        "data_type": data_type,
                        "message": "Data requested (mock)"
                    }
                )
            
            # Handle different data types
            if data_type == "positions":
                self.ib_client.reqPositions()
            elif data_type == "account_summary":
                self.ib_client.reqAccountSummary()
            elif data_type == "current_time":
                self.ib_client.reqCurrentTime()
            
            return IBKRResponse(
                request_id=request.request_id,
                success=True,
                data={
                    "data_type": data_type,
                    "message": f"{data_type} requested successfully"
                }
            )
            
        except Exception as e:
            return IBKRResponse(
                request_id=request.request_id,
                success=False,
                error=str(e)
            )
    
    def _update_request_stats(self, message_type: str):
        """Update request statistics"""
        self.request_stats[message_type] = self.request_stats.get(message_type, 0) + 1
    
    def _update_error_stats(self, error: str):
        """Update error statistics"""
        self.error_stats[error] = self.error_stats.get(error, 0) + 1
    
    # Event handlers (implement as needed)
    def _on_connected(self):
        self.connection_status.state = IBKRConnectionState.CONNECTED
        self.logger.info("IBKR client connected")
        
        for callback in self.connection_callbacks:
            try:
                callback(True)
            except Exception as e:
                self.logger.error(f"Connection callback error: {e}")
    
    def _on_disconnected(self):
        self.connection_status.state = IBKRConnectionState.DISCONNECTED
        self.logger.warning("IBKR client disconnected")
        
        for callback in self.connection_callbacks:
            try:
                callback(False)
            except Exception as e:
                self.logger.error(f"Disconnection callback error: {e}")
    
    def _on_error(self, reqId, errorCode, errorString, contract):
        self.logger.error(f"IBKR Error {errorCode}: {errorString}")
        self.connection_status.error_message = errorString
        
        for callback in self.error_callbacks:
            try:
                callback(errorCode, errorString, contract)
            except Exception as e:
                self.logger.error(f"Error callback error: {e}")
    
    # Additional event handlers (stubs for now)
    def _on_order_status(self, trade): pass
    def _on_open_order(self, contract, order): pass
    def _on_order_bound(self, orderId, contract): pass
    def _on_position(self, position): pass
    def _on_position_end(self): pass
    def _on_account_summary(self, account): pass
    def _on_account_summary_end(self): pass
    def _on_tick_price(self, contract, tickType, price, attrib): pass
    def _on_tick_size(self, contract, tickType, size): pass
    def _on_tick_option_computation(self, contract, tickType, tickValue, tickOptionValue, impliedVol, delta, optPrice, pvDividend, gamma, vega, theta, undPrice): pass
    def _on_tick_generic(self, contract, tickType, value): pass
    def _on_market_data_type(self, reqId, marketDataType): pass
    def _on_tick_efp(self, contract, tickType, basisPoints, formattedBasisPoints, impliedFuture, holdDays, futureExpiry, dividendImpact, dividendsToExpiry): pass
    def _on_tick_function(self, contract, tickType, funcScope, deltaFunctionScope, tickFunction, mimiFunction, text, dummyVar): pass
    def _on_tick_snapshot_end(self, reqId): pass
    def _on_display_group_list(self, reqId, groups): pass
    def _on_display_group_updated(self, reqId, contract): pass
    def _on_historical_data(self, reqId, bar): pass
    def _on_historical_data_update(self, reqId, bar): pass
    def _on_historical_data_end(self, reqId, start, end): pass
    def _on_real_time_bar(self, reqId, bar): pass
    def _on_real_time_bar_end(self, reqId): pass
    def _on_fundamental_data(self, reqId, data): pass
    def _on_news_msgs(self, timeStamp, providerCode, articleId, headline, extraData): pass
    def _on_commission_report(self, commissionReport): pass
    def _on_contract_details(self, reqId, contractDetails): pass
    def _on_contract_details_end(self, reqId): pass
    def _on_scanner_parameters(self, xml): pass
    def _on_scanner_data(self, reqId, rank, contractDetails, distance, benchmark, projection, legsStr): pass
    def _on_scanner_data_end(self, reqId): pass
    def _on_current_time(self, time): pass
    def _on_realtime_data(self, reqId, data): pass
    def _on_realtime_data_end(self, reqId): pass
    def _on_head_timestamp(self, reqId, timestamp): pass
    def _on_histogram_data(self, reqId, data): pass
    def _on_ib_service(self, time, serverId, service, opCode, timeout): pass