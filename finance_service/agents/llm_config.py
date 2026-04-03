"""
TradingAgents Configuration Module

Provides configuration for TradingAgents framework integration
"""

import os
from typing import Dict, Any


def get_agent_config() -> Dict[str, Any]:
    """
    Get TradingAgents configuration from environment variables
    
    Returns:
        Dictionary with TradingAgents configuration
    """
    return {
        # LLM Provider Settings
        "llm_provider": os.getenv("LLM_PROVIDER", "openrouter"),
        "openrouter_api_key": os.getenv("OPENROUTER_API_KEY", ""),
        "openai_api_key": os.getenv("OPENAI_API_KEY", ""),
        "google_api_key": os.getenv("GOOGLE_API_KEY", ""),
        "anthropic_api_key": os.getenv("ANTHROPIC_API_KEY", ""),
        "xai_api_key": os.getenv("XAI_API_KEY", ""),
        
        # Model Configuration
        "quick_think_llm": os.getenv("TA_QUICK_THINK_MODEL", "claude-3.5-sonnet-20241022"),
        "deep_think_llm": os.getenv("TA_DEEP_THINK_MODEL", "claude-3.5-sonnet-20241022"),
        
        # Pipeline Settings
        "debug": os.getenv("TA_DEBUG_MODE", "true").lower() == "true",
        "max_debate_rounds": int(os.getenv("TA_MAX_DEBATE_ROUNDS", "2")),
        "timeout_seconds": int(os.getenv("TA_RESPONSE_TIMEOUT", "30")),
        
        # Feature Flags
        "enable_sentiment": os.getenv("TA_ENABLE_SENTIMENT", "true").lower() == "true",
        "enable_news": os.getenv("TA_ENABLE_NEWS", "true").lower() == "true",
        "enable_technical": os.getenv("TA_ENABLE_TECHNICAL", "true").lower() == "true",
        "enable_fundamental": os.getenv("TA_ENABLE_FUNDAMENTAL", "true").lower() == "true",
        
        # Backtesting
        "backtest_enabled": os.getenv("TA_BACKTEST_ENABLED", "true").lower() == "true",
        "backtest_lookback_days": int(os.getenv("TA_BACKTEST_LOOKBACK_DAYS", "252")),
        
        # Cache Settings
        "cache_enabled": os.getenv("TA_CACHE_ENABLED", "true").lower() == "true",
        "cache_ttl_seconds": int(os.getenv("TA_CACHE_TTL", "300")),
    }


def validate_config() -> bool:
    """
    Validate that all required configuration is present
    
    Returns:
        True if valid, raises exception otherwise
    """
    config = get_agent_config()
    
    if not config["llm_provider"]:
        raise ValueError("LLM_PROVIDER not configured")
    
    provider = config["llm_provider"].lower()
    
    if provider == "openrouter" and not config["openrouter_api_key"]:
        raise ValueError("OPENROUTER_API_KEY not configured")
    elif provider == "openai" and not config["openai_api_key"]:
        raise ValueError("OPENAI_API_KEY not configured")
    elif provider == "google" and not config["google_api_key"]:
        raise ValueError("GOOGLE_API_KEY not configured")
    elif provider == "anthropic" and not config["anthropic_api_key"]:
        raise ValueError("ANTHROPIC_API_KEY not configured")
    
    return True
