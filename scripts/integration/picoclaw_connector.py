"""
PicoClaw Finance Service Connector

Bridges PicoClaw with Finance Service backend
"""
import requests
import json
from typing import Dict, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class FinanceServiceConnector:
    """
    Connector for PicoClaw to communicate with Finance Service
    
    Usage in PicoClaw:
        connector = FinanceServiceConnector("http://localhost:8801")
        result = connector.analyze("AAPL")
    """
    
    def __init__(self, base_url: str = "http://localhost:8801", timeout: int = 30):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.session = requests.Session()
    
    def health_check(self) -> bool:
        """Check if Finance Service is running"""
        try:
            response = self.session.get(
                f"{self.base_url}/health",
                timeout=self.timeout
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
    
    def analyze(self, symbol: str, lookback_days: Optional[int] = None) -> Dict[str, Any]:
        """
        Analyze a stock symbol
        
        Returns: Decision dict with BUY/SELL/HOLD recommendation
        """
        payload = {"symbol": symbol.upper()}
        if lookback_days:
            payload["lookback_days"] = lookback_days
        
        try:
            response = self.session.post(
                f"{self.base_url}/analyze",
                json=payload,
                timeout=self.timeout
            )
            return response.json()
        except Exception as e:
            logger.error(f"Analysis failed for {symbol}: {e}")
            return {"error": str(e), "symbol": symbol}
    
    def get_quote(self, symbol: str) -> Dict[str, Any]:
        """Get latest quote for a symbol"""
        try:
            response = self.session.get(
                f"{self.base_url}/quote/{symbol.upper()}",
                timeout=self.timeout
            )
            return response.json()
        except Exception as e:
            logger.error(f"Quote fetch failed for {symbol}: {e}")
            return {"error": str(e), "symbol": symbol}
    
    def propose_trade(self, decision: Dict[str, Any]) -> Dict[str, Any]:
        """Propose a trade (dry-run validation)"""
        try:
            response = self.session.post(
                f"{self.base_url}/portfolio/propose",
                json=decision,
                timeout=self.timeout
            )
            return response.json()
        except Exception as e:
            logger.error(f"Trade proposal failed: {e}")
            return {"error": str(e), "valid": False}
    
    def execute_trade(self, task_id: str, approval_id: str = "") -> Dict[str, Any]:
        """Execute a proposed trade"""
        payload = {"task_id": task_id, "approval_id": approval_id}
        try:
            response = self.session.post(
                f"{self.base_url}/portfolio/execute",
                json=payload,
                timeout=self.timeout
            )
            return response.json()
        except Exception as e:
            logger.error(f"Trade execution failed: {e}")
            return {"error": str(e), "success": False}
    
    def get_portfolio(self) -> Dict[str, Any]:
        """Get current portfolio state"""
        try:
            response = self.session.get(
                f"{self.base_url}/portfolio/state",
                timeout=self.timeout
            )
            return response.json()
        except Exception as e:
            logger.error(f"Portfolio fetch failed: {e}")
            return {"error": str(e)}
    
    def get_performance(self) -> Dict[str, Any]:
        """Get portfolio performance metrics"""
        try:
            response = self.session.get(
                f"{self.base_url}/portfolio/performance",
                timeout=self.timeout
            )
            return response.json()
        except Exception as e:
            logger.error(f"Performance fetch failed: {e}")
            return {"error": str(e)}


# Singleton instance
_connector = None

def get_connector(base_url: str = "http://localhost:8801") -> FinanceServiceConnector:
    """Get or create connector instance"""
    global _connector
    if _connector is None:
        _connector = FinanceServiceConnector(base_url)
    return _connector


# PicoClaw Tool Functions (expose to PicoClaw)

def analyze_symbol(symbol: str, **kwargs) -> Dict[str, Any]:
    """
    PicoClaw tool: Analyze symbol
    
    Args:
        symbol: Stock ticker (e.g., "AAPL")
    
    Returns:
        Full analysis with signals and decision
    """
    connector = get_connector()
    return connector.analyze(symbol)


def get_price_quote(symbol: str) -> Dict[str, Any]:
    """
    PicoClaw tool: Get latest quote
    
    Args:
        symbol: Stock ticker
    
    Returns:
        Latest price + bid/ask
    """
    connector = get_connector()
    return connector.get_quote(symbol)


def portfolio_state() -> Dict[str, Any]:
    """
    PicoClaw tool: Get portfolio state
    
    Returns:
        Cash, positions, total value, PnL
    """
    connector = get_connector()
    return connector.get_portfolio()


def portfolio_performance() -> Dict[str, Any]:
    """
    PicoClaw tool: Get performance metrics
    
    Returns:
        Returns, Sharpe, drawdown, etc.
    """
    connector = get_connector()
    return connector.get_performance()


def execute_trade_proposal(task_id: str, approval_response: str = "YES") -> Dict[str, Any]:
    """
    PicoClaw tool: Execute trade after approval
    
    Args:
        task_id: From analyze result
        approval_response: "YES" or "NO"
    
    Returns:
        Execution result
    """
    if approval_response.upper() == "NO":
        return {"success": False, "message": "Trade rejected by user"}
    
    connector = get_connector()
    approval_id = f"picoclaw_{datetime.utcnow().isoformat()}"
    return connector.execute_trade(task_id, approval_id)
