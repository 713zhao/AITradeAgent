"""
LLM Analysis Logger for Phase 3 Pre-Selection Pipeline.

Provides structured logging for Phase 3 LLM analysis results:
- Market Regime Analysis (5 indices, risk regime, volatility, trend)
- Macro News Analysis (market sentiment, catalysts, sentiment score)
- Symbol Selector LLM Ranking (50 candidates → top 5-10 picks, scoring breakdown)

Logs are saved in logs/llm_analysis/ with daily files for easy review and debugging.

Usage:
    from finance_service.utils.llm_analysis_logger import LLMAnalysisLogger
    
    logger = LLMAnalysisLogger()
    logger.log_market_regime_analysis("HK", regime_data)
    logger.log_macro_news_analysis("US", news_data)
    logger.log_symbol_selector_ranking("US", candidates, ranked_symbols)
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import os

logger = logging.getLogger(__name__)


class LLMAnalysisLogger:
    """Structured logger for Phase 3 LLM analysis results."""

    def __init__(self, logs_dir: str = "logs/llm_analysis"):
        """
        Initialize LLM analysis logger.
        
        Args:
            logs_dir: Directory for LLM analysis logs (relative to workspace root)
        """
        # Get workspace root (go up from finance_service/utils)
        workspace_root = Path(__file__).parent.parent.parent
        self.logs_dir = workspace_root / logs_dir
        
        # Create logs directory if it doesn't exist
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        
        # Get today's date for daily log file
        today = datetime.now().strftime("%Y-%m-%d")
        self.daily_log_file = self.logs_dir / f"llm_analysis_{today}.json"
        self.daily_summary_file = self.logs_dir / f"llm_analysis_{today}.txt"
        
    def _write_json_log(self, log_entry: Dict[str, Any]) -> None:
        """Append JSON entry to daily log file."""
        try:
            existing_entries = []
            if self.daily_log_file.exists():
                with open(self.daily_log_file, "r") as f:
                    try:
                        existing_entries = json.load(f)
                    except json.JSONDecodeError:
                        existing_entries = []
            
            existing_entries.append(log_entry)
            
            with open(self.daily_log_file, "w") as f:
                json.dump(existing_entries, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to write JSON analysis log: {e}")

    def _write_text_log(self, text: str) -> None:
        """Append text entry to daily summary file."""
        try:
            with open(self.daily_summary_file, "a") as f:
                f.write(text + "\n")
        except Exception as e:
            logger.error(f"Failed to write text analysis log: {e}")

    def log_market_regime_analysis(
        self,
        market: str,
        regime_data: Dict[str, Any],
        indices_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Log Market Regime analysis results.
        
        Args:
            market: "HK" or "US"
            regime_data: {
                "regime_label": "Risk-On" | "Risk-Off",
                "vix": float,
                "volatility_regime": "Low" | "Normal" | "High",
                "trend_strength": float (0-1),
                "sma_position": "Above" | "Below" | "Mixed",
                ...
            }
            indices_data: Optional detailed data for each index
        """
        timestamp = datetime.now().isoformat()
        
        json_entry = {
            "timestamp": timestamp,
            "agent": "MarketRegimeAgent",
            "market": market,
            "regime_data": regime_data,
            "indices_data": indices_data or {},
        }
        
        self._write_json_log(json_entry)
        
        # Write human-readable summary
        summary_text = f"""
{'='*80}
[{timestamp}] Market Regime Analysis - {market} Market
{'='*80}
Regime Label: {regime_data.get('regime_label', 'Unknown')}
VIX Level: {regime_data.get('vix', 'N/A')}
Volatility Regime: {regime_data.get('volatility_regime', 'Unknown')}
Trend Strength: {regime_data.get('trend_strength', 'N/A')}
SMA Position: {regime_data.get('sma_position', 'Unknown')}

Regime Reasoning: {regime_data.get('reasoning', 'N/A')}

Full Regime Data:
{json.dumps(regime_data, indent=2)}
"""
        self._write_text_log(summary_text)
        logger.info(f"Logged MarketRegimeAgent analysis for {market}")

    def log_macro_news_analysis(
        self,
        market: str,
        news_data: Dict[str, Any],
    ) -> None:
        """
        Log Macro News analysis results.
        
        Args:
            market: "HK" or "US"
            news_data: {
                "sentiment_score": float (-1.0 to 1.0),
                "sentiment_label": "Bullish" | "Neutral" | "Bearish",
                "news_count": int,
                "categories": {
                    "monetary_policy": count,
                    "geopolitical": count,
                    "economic_data": count,
                    "regulatory": count,
                    "sector_rotation": count,
                    ...
                },
                "top_catalysts": [
                    {"title": str, "sentiment": float, "category": str},
                    ...
                ],
                ...
            }
        """
        timestamp = datetime.now().isoformat()
        
        json_entry = {
            "timestamp": timestamp,
            "agent": "MacroNewsAgent",
            "market": market,
            "news_data": news_data,
        }
        
        self._write_json_log(json_entry)
        
        # Write human-readable summary
        top_catalysts = news_data.get("top_catalysts", [])
        catalysts_text = ""
        for i, catalyst in enumerate(top_catalysts[:5], 1):
            catalysts_text += f"  {i}. [{catalyst.get('category', 'Unknown')}] {catalyst.get('title', 'N/A')} (Sentiment: {catalyst.get('sentiment', 'N/A')})\n"
        
        categories_text = ""
        for cat, count in news_data.get("categories", {}).items():
            categories_text += f"  • {cat}: {count}\n"
        
        summary_text = f"""
{'='*80}
[{timestamp}] Macro News Analysis - {market} Market
{'='*80}
Sentiment Score: {news_data.get('sentiment_score', 'N/A')} ({news_data.get('sentiment_label', 'Unknown')})
Total News Items: {news_data.get('news_count', 'N/A')}

News Categories:
{categories_text}

Top Catalysts:
{catalysts_text}

Full News Data:
{json.dumps(news_data, indent=2)}
"""
        self._write_text_log(summary_text)
        logger.info(f"Logged MacroNewsAgent analysis for {market}")

    def log_symbol_selector_ranking(
        self,
        market: str,
        candidate_count: int,
        ranked_symbols: List[Dict[str, Any]],
        llm_token_usage: Optional[Dict[str, int]] = None,
        ranking_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Log SymbolSelectorAgent LLM ranking results.
        
        Args:
            market: "HK" or "US"
            candidate_count: Number of candidates evaluated (e.g., 50)
            ranked_symbols: [
                {
                    "symbol": str,
                    "score": float (0-100),
                    "reasoning": str,
                    "rank": int,
                },
                ...
            ]
            llm_token_usage: {
                "prompt_tokens": int,
                "completion_tokens": int,
                "total_tokens": int,
            }
            ranking_data: Optional detailed scoring breakdown
        """
        timestamp = datetime.now().isoformat()
        
        json_entry = {
            "timestamp": timestamp,
            "agent": "SymbolSelectorAgent",
            "market": market,
            "candidate_count": candidate_count,
            "ranked_symbols_count": len(ranked_symbols),
            "ranked_symbols": ranked_symbols,
            "llm_token_usage": llm_token_usage or {},
            "ranking_data": ranking_data or {},
        }
        
        self._write_json_log(json_entry)
        
        # Write human-readable summary
        ranked_text = ""
        for sym in ranked_symbols[:10]:
            ranked_text += f"  {sym.get('rank', '?')}. {sym.get('symbol', 'Unknown')} (Score: {sym.get('score', 'N/A')}/100)\n"
            if sym.get('reasoning'):
                ranked_text += f"     Reason: {sym.get('reasoning', 'N/A')}\n"
        
        token_text = ""
        if llm_token_usage:
            token_text = f"""
LLM Token Usage:
  • Prompt tokens: {llm_token_usage.get('prompt_tokens', 'N/A')}
  • Completion tokens: {llm_token_usage.get('completion_tokens', 'N/A')}
  • Total tokens: {llm_token_usage.get('total_tokens', 'N/A')}
"""
        
        summary_text = f"""
{'='*80}
[{timestamp}] Symbol Selector LLM Ranking - {market} Market
{'='*80}
Candidates Evaluated: {candidate_count}
Selected Symbols: {len(ranked_symbols)} (Final picks from 50 candidates)

Top Ranked Symbols:
{ranked_text}
{token_text}

Full Ranking Data:
{json.dumps(json_entry, indent=2)}
"""
        self._write_text_log(summary_text)
        logger.info(f"Logged SymbolSelectorAgent ranking for {market} ({candidate_count} → {len(ranked_symbols)})")

    def log_llm_call(
        self,
        agent: str,
        prompt_summary: str,
        response_summary: str,
        token_count: Optional[int] = None,
        latency_ms: Optional[float] = None,
        error: Optional[str] = None,
    ) -> None:
        """
        Log individual LLM API calls for debugging.
        
        Args:
            agent: Agent name ("MarketRegimeAgent", "MacroNewsAgent", "SymbolSelectorAgent")
            prompt_summary: Brief summary of the prompt
            response_summary: Brief summary of the response
            token_count: Total tokens used
            latency_ms: API call latency in milliseconds
            error: Error message if API call failed
        """
        timestamp = datetime.now().isoformat()
        
        json_entry = {
            "timestamp": timestamp,
            "type": "LLM_CALL",
            "agent": agent,
            "prompt_summary": prompt_summary,
            "response_summary": response_summary,
            "token_count": token_count,
            "latency_ms": latency_ms,
            "error": error,
        }
        
        self._write_json_log(json_entry)
        
        status = "✅ SUCCESS" if not error else "❌ FAILED"
        latency_text = f" ({latency_ms:.1f}ms)" if latency_ms else ""
        error_text = f"\nError: {error}" if error else ""
        
        summary_text = f"""
[{timestamp}] {status} LLM API Call - {agent}{latency_text}
├─ Prompt: {prompt_summary[:100]}...
├─ Response: {response_summary[:100]}...
└─ Tokens: {token_count or 'N/A'}{error_text}
"""
        self._write_text_log(summary_text)
        logger.debug(f"Logged LLM call for {agent}: {status}")

    def log_phase3_daily_summary(
        self,
        summary_data: Dict[str, Any],
    ) -> None:
        """
        Log daily Phase 3 execution summary.
        
        Args:
            summary_data: {
                "date": str (YYYY-MM-DD),
                "market_regime_runs": int,
                "macro_news_runs": int,
                "symbol_selector_runs": int,
                "total_symbols_processed": int,
                "top_picks_count": int,
                "error_count": int,
                "total_tokens_used": int,
            }
        """
        timestamp = datetime.now().isoformat()
        
        json_entry = {
            "timestamp": timestamp,
            "type": "DAILY_SUMMARY",
            "summary_data": summary_data,
        }
        
        self._write_json_log(json_entry)
        
        summary_text = f"""
{'*'*80}
[{timestamp}] PHASE 3 LLM PRE-SELECTION PIPELINE - DAILY SUMMARY
{'*'*80}
Date: {summary_data.get('date', 'N/A')}

Execution Metrics:
  • Market Regime Runs: {summary_data.get('market_regime_runs', 'N/A')}
  • Macro News Runs: {summary_data.get('macro_news_runs', 'N/A')}
  • Symbol Selector Runs: {summary_data.get('symbol_selector_runs', 'N/A')}

Processing Stats:
  • Total Symbols Processed: {summary_data.get('total_symbols_processed', 'N/A')}
  • Final Top Picks: {summary_data.get('top_picks_count', 'N/A')}
  • Total LLM Tokens Used: {summary_data.get('total_tokens_used', 'N/A')}
  • Errors: {summary_data.get('error_count', 'N/A')}

{'*'*80}
"""
        self._write_text_log(summary_text)
        logger.info(f"Logged Phase 3 daily summary for {summary_data.get('date', 'today')}")

    def get_analysis_logs_dir(self) -> str:
        """Get the LLM analysis logs directory path."""
        return str(self.logs_dir)

    def get_today_log_file(self) -> str:
        """Get today's log file path (JSON format)."""
        return str(self.daily_log_file)

    def get_today_summary_file(self) -> str:
        """Get today's summary file path (human-readable format)."""
        return str(self.daily_summary_file)


# Global logger instance
_global_logger: Optional[LLMAnalysisLogger] = None


def get_llm_analysis_logger() -> LLMAnalysisLogger:
    """Get or create the global LLM analysis logger instance."""
    global _global_logger
    if _global_logger is None:
        _global_logger = LLMAnalysisLogger()
    return _global_logger
