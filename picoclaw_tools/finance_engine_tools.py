"""
PicoClaw Finance Engine Tool Handlers
Connects PicoClaw to picotradeagent Finance Service via HTTP REST
"""

import httpx
import json
import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

# Configuration
FINANCE_ENGINE_URL = "http://localhost:8801"
DEFAULT_TIMEOUT = 30


class FinanceEngineClient:
    """HTTP client for Finance Engine API"""

    def __init__(self, base_url: str = FINANCE_ENGINE_URL, timeout: int = DEFAULT_TIMEOUT):
        self.base_url = base_url
        self.timeout = timeout
        self.client = httpx.Client(timeout=timeout)

    def _call_endpoint(self, method: str, path: str, payload: Dict[str, Any] = None) -> Dict[str, Any]:
        """Make HTTP request to Finance Engine"""
        url = urljoin(self.base_url, path)
        try:
            if method == "GET":
                r = self.client.get(url)
            elif method == "POST":
                r = self.client.post(url, json=payload or {})
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as e:
            logger.error(f"HTTP error calling {url}: {e}")
            return {"error": str(e), "status": "failed"}
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error from {url}: {e}")
            return {"error": str(e), "status": "failed"}

    def close(self):
        """Close HTTP client"""
        self.client.close()


# Global client instance
_client = FinanceEngineClient()


def data_agent_fetch(symbols: List[str], timeframe: str, lookback_days: int = 365) -> Dict[str, Any]:
    """Data Agent: Fetch OHLCV data"""
    payload = {"symbols": symbols, "timeframe": timeframe, "lookback_days": lookback_days}
    return _client._call_endpoint("POST", "/agents/data/fetch", payload)


def analysis_agent_indicators(symbol: str, timeframe: str) -> Dict[str, Any]:
    """Analysis Agent: Calculate indicators"""
    payload = {"symbol": symbol, "timeframe": timeframe}
    return _client._call_endpoint("POST", "/agents/analysis/indicators", payload)


def strategy_agent_decide(symbol: str, timeframe: str) -> Dict[str, Any]:
    """Strategy Agent: Generate signal"""
    payload = {"symbol": symbol, "timeframe": timeframe}
    return _client._call_endpoint("POST", "/agents/strategy/decide", payload)


def risk_agent_validate(symbol: str, side: str, confidence: float, timeframe: str, proposed_qty: Optional[int] = None) -> Dict[str, Any]:
    """Risk Agent: Validate trade"""
    payload = {"symbol": symbol, "side": side, "confidence": confidence, "timeframe": timeframe, "proposed_qty": proposed_qty}
    return _client._call_endpoint("POST", "/agents/risk/validate", payload)


def execution_agent_paper_trade(symbol: str, side: str, qty: int, timeframe: str, reason: str = "") -> Dict[str, Any]:
    """Execution Agent: Execute trade"""
    payload = {"symbol": symbol, "side": side, "qty": qty, "timeframe": timeframe, "reason": reason}
    return _client._call_endpoint("POST", "/agents/execution/paper_trade", payload)


def learning_agent_run(mode: str = "dry_run") -> Dict[str, Any]:
    """Learning Agent: Run optimization"""
    payload = {"mode": mode}
    return _client._call_endpoint("POST", "/agents/learning/run", payload)


def engine_status() -> Dict[str, Any]:
    """Get portfolio status"""
    return _client._call_endpoint("GET", "/status")


def engine_positions() -> Dict[str, Any]:
    """List open positions"""
    return _client._call_endpoint("GET", "/positions")


def engine_trade_history(symbol: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
    """Query trade history"""
    payload = {"symbol": symbol, "limit": limit}
    return _client._call_endpoint("POST", "/trades", payload)


def engine_set_focus(theme: Optional[str] = None, keywords: Optional[List[str]] = None, watchlist: Optional[List[str]] = None) -> Dict[str, Any]:
    """Update trading focus"""
    payload = {"theme": theme, "keywords": keywords, "watchlist": watchlist}
    return _client._call_endpoint("POST", "/config/focus", payload)


def engine_pause() -> Dict[str, Any]:
    """Pause trading loop"""
    return _client._call_endpoint("POST", "/control/pause", {})


def engine_resume() -> Dict[str, Any]:
    """Resume trading loop"""
    return _client._call_endpoint("POST", "/control/resume", {})


def engine_reset_portfolio(cash: float = 100000) -> Dict[str, Any]:
    """Reset portfolio"""
    payload = {"cash": cash}
    return _client._call_endpoint("POST", "/control/reset", payload)


def engine_last_report(report_type: str) -> Dict[str, Any]:
    """Get last report"""
    payload = {"type": report_type}
    return _client._call_endpoint("POST", "/reports/last", payload)


def cleanup():
    """Close client connection"""
    _client.close()
