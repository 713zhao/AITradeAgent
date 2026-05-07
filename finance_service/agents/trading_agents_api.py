"""
TradingAgents REST API Endpoints

Provides REST endpoints for TradingAgents analysis integration.
"""

from flask import Blueprint, request, jsonify
from typing import Dict, Any
import logging

from finance_service.agents import TradingAgentsAnalyzer

logger = logging.getLogger(__name__)

# Create Blueprint for TradingAgents routes
trading_agents_bp = Blueprint("trading_agents", __name__, url_prefix="/agents/trading-agents")

# Global analyzer instance (lazy-initialized)
_analyzer: TradingAgentsAnalyzer = None


def get_analyzer() -> TradingAgentsAnalyzer:
    """Get or create the TradingAgents analyzer instance"""
    global _analyzer
    if _analyzer is None:
        _analyzer = TradingAgentsAnalyzer(enable_cache=True)
    return _analyzer


@trading_agents_bp.route("/health", methods=["GET"])
def ta_health():
    """Health check for TradingAgents service"""
    try:
        analyzer = get_analyzer()
        config = analyzer.config
        
        return jsonify({
            "status": "ok",
            "service": "trading-agents",
            "llm_provider": config["llm_provider"],
            "initialized": analyzer._initialized,
            "cache": analyzer.get_cache_stats()
        }), 200
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            "status": "error",
            "service": "trading-agents",
            "error": str(e)
        }), 503


@trading_agents_bp.route("/analyze", methods=["POST"])
def ta_analyze():
    """
    Run full TradingAgents analysis on a symbol.
    
    Request body: {"symbol": "NVDA", "analysis_date": "2026-04-02"}
    """
    try:
        data = request.get_json() or {}
        symbol = data.get("symbol", "").upper()
        analysis_date = data.get("analysis_date")
        
        if not symbol:
            return jsonify({
                "status": "error",
                "error": "Missing required field: symbol"
            }), 400
        
        logger.info(f"TradingAgents analysis requested for {symbol}")
        
        analyzer = get_analyzer()
        result = analyzer.analyze(symbol, analysis_date)
        
        return jsonify(result), 200 if result.get("status") == "success" else 500
        
    except Exception as e:
        logger.error(f"TradingAgents analysis error: {e}")
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500


@trading_agents_bp.route("/cache/stats", methods=["GET"])
def ta_cache_stats():
    """Get cache statistics"""
    try:
        analyzer = get_analyzer()
        stats = analyzer.get_cache_stats()
        
        return jsonify({
            "status": "ok",
            "cache": stats
        }), 200
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500


def register_trading_agents_routes(app):
    """Register TradingAgents Blueprint with Flask app"""
    app.register_blueprint(trading_agents_bp)
    logger.info("Registered TradingAgents routes at /agents/trading-agents")
