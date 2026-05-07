"""
TradingAgents Analyzer

Main integration point for TradingAgents framework.
Provides multi-agent analysis for trading signals.
"""

import logging
from typing import Dict, Any, Optional, AsyncGenerator
from datetime import datetime, timedelta
import asyncio
import json

from .llm_config import get_agent_config, validate_config

logger = logging.getLogger(__name__)


class TradingAgentsAnalyzer:
    """
    Analyzer using TradingAgents framework for AI-powered analysis.
    
    Supports:
    - Fundamental analysis
    - Sentiment analysis
    - News analysis
    - Technical analysis
    - Debate-based decision making
    """
    
    def __init__(self, enable_cache: bool = True):
        """
        Initialize TradingAgents analyzer
        
        Args:
            enable_cache: Whether to cache analysis results
        """
        self.config = get_agent_config()
        validate_config()
        
        self.enable_cache = enable_cache and self.config["cache_enabled"]
        self.cache_ttl = self.config["cache_ttl_seconds"]
        self._cache: Dict[str, tuple[Any, datetime]] = {}
        
        self._trading_agents_graph = None
        self._initialized = False
        
        logger.info(f"TradingAgentsAnalyzer initialized with provider: {self.config['llm_provider']}")
    
    def _lazy_init(self):
        """Initialize TradingAgents graph on first use (lazy loading)"""
        if self._initialized:
            return
        
        try:
            from tradingagents.graph.trading_graph import TradingAgentsGraph
            from tradingagents.default_config import DEFAULT_CONFIG
            
            config = DEFAULT_CONFIG.copy()
            config["llm_provider"] = self.config["llm_provider"]
            config["deep_think_llm"] = self.config["deep_think_llm"]
            config["quick_think_llm"] = self.config["quick_think_llm"]
            config["max_debate_rounds"] = self.config["max_debate_rounds"]
            config["debug"] = self.config["debug"]
            
            # Set API keys
            if self.config["llm_provider"] == "openrouter":
                config["openrouter_api_key"] = self.config["openrouter_api_key"]
            elif self.config["llm_provider"] == "openai":
                config["openai_api_key"] = self.config["openai_api_key"]
            elif self.config["llm_provider"] == "google":
                config["google_api_key"] = self.config["google_api_key"]
            elif self.config["llm_provider"] == "anthropic":
                config["anthropic_api_key"] = self.config["anthropic_api_key"]
            
            self._trading_agents_graph = TradingAgentsGraph(debug=config["debug"], config=config)
            self._initialized = True
            logger.info("TradingAgents graph initialized successfully")
            
        except ImportError as e:
            logger.error(f"TradingAgents not installed: {e}. Install with: pip install tradingagents")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize TradingAgents: {e}")
            raise
    
    def _get_cache_key(self, symbol: str, analysis_date: Optional[str] = None) -> str:
        """Generate cache key for analysis"""
        date_str = analysis_date or datetime.now().strftime("%Y-%m-%d")
        return f"ta_analysis:{symbol}:{date_str}"
    
    def _check_cache(self, symbol: str, analysis_date: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Check if cached analysis exists and is valid"""
        if not self.enable_cache:
            return None
        
        cache_key = self._get_cache_key(symbol, analysis_date)
        if cache_key in self._cache:
            cached_result, cached_time = self._cache[cache_key]
            if datetime.now() - cached_time < timedelta(seconds=self.cache_ttl):
                logger.debug(f"Cache hit for {symbol}")
                return cached_result
            else:
                del self._cache[cache_key]
        
        return None
    
    def _store_cache(self, symbol: str, result: Dict[str, Any], analysis_date: Optional[str] = None):
        """Store analysis in cache"""
        if not self.enable_cache:
            return
        
        cache_key = self._get_cache_key(symbol, analysis_date)
        self._cache[cache_key] = (result, datetime.now())
    
    def analyze(self, symbol: str, analysis_date: Optional[str] = None) -> Dict[str, Any]:
        """
        Perform full TradingAgents analysis on a symbol.
        
        This runs the complete multi-agent framework:
        - Analyst team evaluates data
        - Researchers debate insights
        - Trader makes final decision
        - Risk management validates trade
        
        Args:
            symbol: Stock ticker symbol (e.g., "NVDA")
            analysis_date: Analysis date as string (YYYY-MM-DD), uses today if not provided
        
        Returns:
            Analysis result with:
            {
                "symbol": str,
                "analysis_date": str,
                "analysts": {...},          # Individual analyst reports
                "decision": str,            # BUY/SELL/HOLD
                "confidence": float,        # 0.0-1.0
                "discussion": str,          # Debate summary
                "risk_summary": str,        # Risk assessment
                "execution": {...}          # Execution details
            }
        """
        # Check cache first
        cached_result = self._check_cache(symbol, analysis_date)
        if cached_result:
            return cached_result
        
        # Lazy init on first use
        self._lazy_init()
        
        try:
            # Use analysis_date if provided, otherwise use today
            if not analysis_date:
                analysis_date = datetime.now().strftime("%Y-%m-%d")
            
            logger.info(f"Starting TradingAgents analysis for {symbol} on {analysis_date}")
            
            # Run the TradingAgents graph
            _, decision = self._trading_agents_graph.propagate(symbol, analysis_date)
            
            # Format result
            result = {
                "symbol": symbol,
                "analysis_date": analysis_date,
                "timestamp": datetime.now().isoformat(),
                "status": "success",
                "decision": {
                    "action": getattr(decision, "action", None),
                    "confidence": getattr(decision, "confidence", 0.0),
                    "rationale": getattr(decision, "rationale", ""),
                },
                "analysis": {
                    "discussion": getattr(decision, "discussion", ""),
                    "risk_assessment": getattr(decision, "risk_assessment", ""),
                },
                "raw_decision": str(decision)
            }
            
            # Store in cache
            self._store_cache(symbol, result, analysis_date)
            
            logger.info(f"Analysis complete for {symbol}: {result['decision']['action']}")
            return result
            
        except Exception as e:
            logger.error(f"Analysis failed for {symbol}: {e}")
            return {
                "symbol": symbol,
                "analysis_date": analysis_date or datetime.now().strftime("%Y-%m-%d"),
                "timestamp": datetime.now().isoformat(),
                "status": "error",
                "error": str(e),
                "decision": {
                    "action": "HOLD",  
                    "confidence": 0.0,
                    "rationale": f"Analysis failed: {str(e)}"
                }
            }
    
    def clear_cache(self):
        """Clear all cached analysis results"""
        self._cache.clear()
        logger.info("Cache cleared")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        valid_items = 0
        expired_items = 0
        
        now = datetime.now()
        for key, (_, cached_time) in list(self._cache.items()):
            if now - cached_time < timedelta(seconds=self.cache_ttl):
                valid_items += 1
            else:
                expired_items += 1
                del self._cache[key]
        
        return {
            "valid_items": valid_items,
            "expired_items": expired_items,
            "cache_size": len(self._cache),
            "cache_enabled": self.enable_cache,
            "cache_ttl_seconds": self.cache_ttl
        }
