"""Strategy interface and base classes"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class StrategyInterface(ABC):
    """Base class for trading strategies"""
    
    def __init__(self, name: str):
        self.name = name
        self.signals: List[Dict] = []
    
    @abstractmethod
    def analyze(self, symbol: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze symbol and generate signals
        
        Args:
            symbol: Ticker symbol
            data: OHLCV data with indicators
        
        Returns:
            Decision dict with action, confidence, signals, rationale
        """
        pass
    
    def _create_decision(self, symbol: str, action: str, confidence: float,
                        signals: Dict[str, Any], rationale: List[str],
                        position: Optional[Dict] = None,
                        risk: Optional[Dict] = None) -> Dict[str, Any]:
        """Helper to create decision dict"""
        return {
            "symbol": symbol,
            "decision": action,
            "confidence": confidence,
            "signals": signals,
            "rationale": rationale,
            "position": position or {},
            "risk": risk or {},
        }
