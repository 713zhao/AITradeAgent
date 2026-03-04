"""
TD Ameritrade (TDA) Client Module

This module provides the low-level client interface for TD Ameritrade API,
handling authentication, request management, and rate limiting.

Key Features:
- OAuth 2.0 authentication flow
- Request rate limiting and queuing
- Error handling and retry logic
- Session management
- Performance monitoring
- Request/response logging

Author: PicotradeAgent
Version: 6.3.0
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Union, Tuple
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
import json
import aiohttp
import base64
import urllib.parse
import hmac
import hashlib

from finance_service.brokers.tda_broker import TDAConfig, TDAConnectionStatus, TDASessionStatus


class TDARequestType(str, Enum):
    """TDA request types"""
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"


class TDARateLimitStatus(str, Enum):
    """Rate limit status"""
    OK = "OK"
    APPROACHING_LIMIT = "APPROACHING_LIMIT"
    AT_LIMIT = "AT_LIMIT"
    EXCEEDED = "EXCEEDED"


@dataclass
class TDARequest:
    """TDA API request wrapper"""
    request_id: str
    method: TDARequestType
    endpoint: str
    data: Optional[Dict[str, Any]] = None
    params: Optional[Dict[str, Any]] = None
    headers: Optional[Dict[str, str]] = None
    timestamp: datetime = field(default_factory=datetime.now)
    timeout: float = 10.0
    retries: int = 0
    max_retries: int = 3
    callback: Optional[Callable] = None


@dataclass
class TDAResponse:
    """TDA API response wrapper"""
    request_id: str
    success: bool
    status_code: int
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    timestamp: datetime = field(default_factory=datetime.now)
    duration: float = 0.0


@dataclass
class TDARateLimitInfo:
    """TDA rate limit information"""
    limit: int
    remaining: int
    reset_time: Optional[datetime] = None
    status: TDARateLimitStatus = TDARateLimitStatus.OK
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "limit": self.limit,
            "remaining": self.remaining,
            "reset_time": self.reset_time.isoformat() if self.reset_time else None,
            "status": self.status.value
        }


class TDARequestManager:
    """
    TDA Request Manager
    
    Manages API requests to TD Ameritrade with rate limiting,
    retry logic, and performance monitoring.
    """
    
    def __init__(self, config: TDAConfig):
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.TDARequestManager")
        
        # Session management
        self.session: Optional[aiohttp.ClientSession] = None
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.token_expires_at: Optional[datetime] = None
        
        # Request tracking
        self.pending_requests: Dict[str, TDARequest] = {}
        self.request_queue: asyncio.Queue = asyncio.Queue()
        self.response_handlers: Dict[str, List[Callable]] = {}
        
        # Rate limiting
        self.rate_limit_info = TDARateLimitInfo(limit=100, remaining=100)
        self.request_times: List[float] = []
        self.burst_requests: List[float] = []
        
        # Performance tracking
        self.request_stats: Dict[str, int] = {}
        self.error_stats: Dict[str, int] = {}
        self.response_times: List[float] = []
        
        # Event callbacks
        self.auth_callbacks: List[Callable] = []
        self.rate_limit_callbacks: List[Callable] = []
        self.error_callbacks: List[Callable] = []
        
        self.logger.info("TDA Request Manager initialized")
    
    async def initialize(self) -> bool:
        """
        Initialize the request manager
        
        Returns:
            bool: True if initialization successful
        """
        try:
            # Create HTTP session
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.config.connection_timeout)
            )
            
            # Load existing tokens if available
            if self.config.access_token:
                self.access_token = self.config.access_token
                self.refresh_token = self.config.refresh_token
                self.token_expires_at = self.config.token_expires_at
            
            # Start request processor
            asyncio.create_task(self._process_request_queue())
            
            self.logger.info("TDA Request Manager initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize TDA Request Manager: {e}")
            return False
    
    async def authenticate(self, auth_code: Optional[str] = None) -> bool:
        """
        Authenticate with TD Ameritrade
        
        Args:
            auth_code: Authorization code from OAuth flow
            
        Returns:
            bool: True if authentication successful
        """
        try:
            self.logger.info("Starting TDA authentication")
            
            if self._is_token_valid():
                self.logger.info("Using existing valid tokens")
                return True
            
            if auth_code:
                # Exchange auth code for tokens
                return await self._exchange_auth_code(auth_code)
            elif self.config.access_token:
                # Use provided token
                self.access_token = self.config.access_token
                self.refresh_token = self.config.refresh_token
                self.token_expires_at = self.config.token_expires_at
                return True
            else:
                self.logger.error("No authentication method available")
                return False
                
        except Exception as e:
            self.logger.error(f"TDA authentication failed: {e}")
            return False
    
    async def refresh_token(self) -> bool:
        """
        Refresh access token
        
        Returns:
            bool: True if refresh successful
        """
        try:
            if not self.refresh_token:
                self.logger.error("No refresh token available")
                return False
            
            self.logger.info("Refreshing TDA access token")
            
            # Prepare refresh request
            refresh_data = {
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
                "client_id": self.config.api_key
            }
            
            async with self.session.post(
                "https://api.tdameritrade.com/v1/oauth2/token",
                data=refresh_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            ) as response:
                if response.status == 200:
                    token_data = await response.json()
                    
                    self.access_token = token_data.get("access_token")
                    self.refresh_token = token_data.get("refresh_token", self.refresh_token)
                    
                    # Calculate expiry time (tokens typically expire in 1 hour)
                    expires_in = token_data.get("expires_in", 3600)
                    self.token_expires_at = datetime.now() + timedelta(seconds=expires_in)
                    
                    self.logger.info("Token refreshed successfully")
                    return True
                else:
                    self.logger.error(f"Token refresh failed: {response.status}")
                    return False
            
        except Exception as e:
            self.logger.error(f"Token refresh error: {e}")
            return False
    
    async def send_request(self, request: TDARequest) -> TDAResponse:
        """
        Send request to TDA API
        
        Args:
            request: Request to send
            
        Returns:
            TDAResponse: Response from TDA API
        """
        try:
            # Add to queue for processing
            await self.request_queue.put(request)
            
            # Wait for response (simplified - would use async events in production)
            start_time = time.time()
            
            # For now, process directly (would be async in production)
            response = await self._execute_request(request)
            
            response.duration = time.time() - start_time
            return response
            
        except Exception as e:
            self.logger.error(f"Error sending request {request.request_id}: {e}")
            return TDAResponse(
                request_id=request.request_id,
                success=False,
                status_code=0,
                error=str(e)
            )
    
    def is_authenticated(self) -> bool:
        """Check if authenticated with TDA"""
        return self._is_token_valid()
    
    def get_rate_limit_info(self) -> TDARateLimitInfo:
        """Get current rate limit information"""
        return self.rate_limit_info
    
    def add_auth_callback(self, callback: Callable):
        """Add authentication status callback"""
        self.auth_callbacks.append(callback)
    
    def add_rate_limit_callback(self, callback: Callable):
        """Add rate limit callback"""
        self.rate_limit_callbacks.append(callback)
    
    def add_error_callback(self, callback: Callable):
        """Add error callback"""
        self.error_callbacks.append(callback)
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics"""
        return {
            "request_stats": self.request_stats.copy(),
            "error_stats": self.error_stats.copy(),
            "avg_response_time": sum(self.response_times) / len(self.response_times) if self.response_times else 0.0,
            "total_requests": sum(self.request_stats.values()),
            "total_errors": sum(self.error_stats.values()),
            "auth_status": "authenticated" if self.is_authenticated() else "not_authenticated",
            "rate_limit": self.rate_limit_info.to_dict()
        }
    
    async def close(self):
        """Close the request manager"""
        if self.session:
            await self.session.close()
    
    # Private methods
    
    def _is_token_valid(self) -> bool:
        """Check if current access token is valid"""
        if not self.access_token or not self.token_expires_at:
            return False
        
        # Check if token expires within 5 minutes
        time_to_expire = self.token_expires_at - datetime.now()
        return time_to_expire.total_seconds() > 300  # 5 minutes
    
    async def _exchange_auth_code(self, auth_code: str) -> bool:
        """Exchange authorization code for access token"""
        try:
            # Prepare token request
            token_data = {
                "grant_type": "authorization_code",
                "access_type": "offline",
                "code": auth_code,
                "client_id": self.config.api_key,
                "redirect_uri": self.config.redirect_uri
            }
            
            async with self.session.post(
                "https://api.tdameritrade.com/v1/oauth2/token",
                data=token_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            ) as response:
                if response.status == 200:
                    token_response = await response.json()
                    
                    self.access_token = token_response.get("access_token")
                    self.refresh_token = token_response.get("refresh_token")
                    
                    # Calculate expiry time
                    expires_in = token_response.get("expires_in", 3600)
                    self.token_expires_at = datetime.now() + timedelta(seconds=expires_in)
                    
                    # Notify callbacks
                    for callback in self.auth_callbacks:
                        try:
                            callback(True)
                        except Exception as e:
                            self.logger.error(f"Auth callback error: {e}")
                    
                    self.logger.info("Authentication successful")
                    return True
                else:
                    error_text = await response.text()
                    self.logger.error(f"Authentication failed: {response.status} - {error_text}")
                    return False
            
        except Exception as e:
            self.logger.error(f"Auth code exchange error: {e}")
            return False
    
    async def _process_request_queue(self):
        """Process requests from the queue"""
        while True:
            try:
                request = await self.request_queue.get()
                
                # Check rate limits
                if not await self._check_rate_limits():
                    # Re-queue for later
                    await asyncio.sleep(1.0)
                    await self.request_queue.put(request)
                    continue
                
                # Execute request
                response = await self._execute_request(request)
                
                # Handle response
                if response.success:
                    self._update_success_stats(request)
                else:
                    self._update_error_stats(request, response.error)
                
                # Call callback if provided
                if request.callback:
                    try:
                        request.callback(response)
                    except Exception as e:
                        self.logger.error(f"Request callback error: {e}")
                
            except Exception as e:
                self.logger.error(f"Request queue processing error: {e}")
                await asyncio.sleep(1.0)
    
    async def _check_rate_limits(self) -> bool:
        """Check and enforce rate limits"""
        current_time = time.time()
        
        # Clean old request times
        self.request_times = [t for t in self.request_times if current_time - t < 1.0]
        self.burst_requests = [t for t in self.burst_requests if current_time - t < 1.0]
        
        # Check burst limit (requests per second)
        if len(self.burst_requests) >= self.config.burst_requests:
            sleep_time = 1.0 - (current_time - self.burst_requests[0])
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
        
        # Check rate limit (requests per minute equivalent)
        if len(self.request_times) >= self.config.requests_per_second:
            sleep_time = 1.0 - (current_time - self.request_times[-self.config.requests_per_second])
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
        
        # Add current request time
        self.request_times.append(current_time)
        self.burst_requests.append(current_time)
        
        # Update rate limit info
        self.rate_limit_info.remaining = max(0, self.rate_limit_info.limit - len(self.request_times))
        
        # Notify if approaching limit
        if self.rate_limit_info.remaining < 10:
            self.rate_limit_info.status = TDARateLimitStatus.APPROACHING_LIMIT
            for callback in self.rate_limit_callbacks:
                try:
                    callback(self.rate_limit_info)
                except Exception as e:
                    self.logger.error(f"Rate limit callback error: {e}")
        
        return True
    
    async def _execute_request(self, request: TDARequest) -> TDAResponse:
        """Execute a single request"""
        try:
            start_time = time.time()
            
            # Prepare headers
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }
            
            if request.headers:
                headers.update(request.headers)
            
            # Prepare URL
            url = f"{self.config.api_base_url}{request.endpoint}"
            
            # Make request
            async with self.session.request(
                method=request.method.value,
                url=url,
                headers=headers,
                json=request.data,
                params=request.params,
                timeout=aiohttp.ClientTimeout(total=request.timeout)
            ) as response:
                # Parse response
                response_data = None
                if response.content_type == "application/json":
                    response_data = await response.json()
                else:
                    response_data = await response.text()
                
                # Handle authentication errors
                if response.status == 401:
                    # Token expired, try to refresh
                    if await self.refresh_token():
                        # Retry request with new token
                        headers["Authorization"] = f"Bearer {self.access_token}"
                        async with self.session.request(
                            method=request.method.value,
                            url=url,
                            headers=headers,
                            json=request.data,
                            params=request.params
                        ) as retry_response:
                            retry_data = await retry_response.json() if retry_response.content_type == "application/json" else await retry_response.text()
                            return TDAResponse(
                                request_id=request.request_id,
                                success=retry_response.status < 400,
                                status_code=retry_response.status,
                                data=retry_data if isinstance(retry_data, dict) else None,
                                error=None if retry_response.status < 400 else f"HTTP {retry_response.status}",
                                headers=dict(retry_response.headers)
                            )
                    else:
                        return TDAResponse(
                            request_id=request.request_id,
                            success=False,
                            status_code=401,
                            error="Authentication failed"
                        )
                
                return TDAResponse(
                    request_id=request.request_id,
                    success=response.status < 400,
                    status_code=response.status,
                    data=response_data if isinstance(response_data, dict) else None,
                    error=None if response.status < 400 else f"HTTP {response.status}",
                    headers=dict(response.headers)
                )
                
        except asyncio.TimeoutError:
            return TDAResponse(
                request_id=request.request_id,
                success=False,
                status_code=408,
                error="Request timeout"
            )
        except Exception as e:
            return TDAResponse(
                request_id=request.request_id,
                success=False,
                status_code=0,
                error=str(e)
            )
    
    def _update_success_stats(self, request: TDARequest):
        """Update success statistics"""
        endpoint = request.endpoint.split("?")[0]  # Remove query params
        self.request_stats[endpoint] = self.request_stats.get(endpoint, 0) + 1
    
    def _update_error_stats(self, request: TDARequest, error: str):
        """Update error statistics"""
        error_key = f"{request.endpoint}:{error}"
        self.error_stats[error_key] = self.error_stats.get(error_key, 0) + 1
        
        # Notify error callbacks
        for callback in self.error_callbacks:
            try:
                callback(request, error)
            except Exception as e:
                self.logger.error(f"Error callback error: {e}")


class TDAClient:
    """
    TDA Client
    
    High-level client interface for TD Ameritrade API operations.
    """
    
    def __init__(self, config: TDAConfig):
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.TDAClient")
        
        self.request_manager = TDARequestManager(config)
    
    async def initialize(self) -> bool:
        """Initialize the client"""
        return await self.request_manager.initialize()
    
    async def authenticate(self, auth_code: Optional[str] = None) -> bool:
        """Authenticate with TDA"""
        return await self.request_manager.authenticate(auth_code)
    
    async def get_account_info(self, account_id: str) -> Optional[Dict[str, Any]]:
        """Get account information"""
        request = TDARequest(
            request_id=f"account_{account_id}_{int(time.time())}",
            method=TDARequestType.GET,
            endpoint=f"/accounts/{account_id}",
            params={"fields": "positions,orders,account"}
        )
        
        response = await self.request_manager.send_request(request)
        return response.data if response.success else None
    
    async def get_positions(self, account_id: str) -> Optional[List[Dict[str, Any]]]:
        """Get account positions"""
        account_info = await self.get_account_info(account_id)
        if account_info and "securitiesAccount" in account_info:
            return account_info["securitiesAccount"].get("positions", [])
        return None
    
    async def place_order(self, account_id: str, order_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Place an order"""
        request = TDARequest(
            request_id=f"order_{int(time.time())}",
            method=TDARequestType.POST,
            endpoint=f"/accounts/{account_id}/orders",
            data=order_data
        )
        
        response = await self.request_manager.send_request(request)
        return response.data if response.success else None
    
    async def cancel_order(self, account_id: str, order_id: str) -> bool:
        """Cancel an order"""
        request = TDARequest(
            request_id=f"cancel_{order_id}_{int(time.time())}",
            method=TDARequestType.DELETE,
            endpoint=f"/accounts/{account_id}/orders/{order_id}"
        )
        
        response = await self.request_manager.send_request(request)
        return response.success
    
    async def get_quotes(self, symbols: List[str]) -> Optional[Dict[str, Any]]:
        """Get market quotes"""
        symbols_param = ",".join(symbols)
        request = TDARequest(
            request_id=f"quotes_{int(time.time())}",
            method=TDARequestType.GET,
            endpoint="/marketdata/quotes",
            params={"symbol": symbols_param}
        )
        
        response = await self.request_manager.send_request(request)
        return response.data if response.success else None
    
    async def get_price_history(self, symbol: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Get price history for a symbol"""
        params = {"symbol": symbol}
        params.update(kwargs)
        
        request = TDARequest(
            request_id=f"history_{symbol}_{int(time.time())}",
            method=TDARequestType.GET,
            endpoint="/marketdata/pricehistory",
            params=params
        )
        
        response = await self.request_manager.send_request(request)
        return response.data if response.success else None
    
    def is_authenticated(self) -> bool:
        """Check if authenticated"""
        return self.request_manager.is_authenticated()
    
    def get_rate_limit_info(self) -> TDARateLimitInfo:
        """Get rate limit information"""
        return self.request_manager.get_rate_limit_info()
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics"""
        return self.request_manager.get_performance_stats()
    
    async def close(self):
        """Close the client"""
        await self.request_manager.close()