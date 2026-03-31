"""Fundamentals data fetching with provider fallback"""
import logging
import time
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class BaseFundamentalsProvider:
    """Base class for fundamentals providers"""
    
    def fetch(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Fetch fundamentals for a symbol. Returns dict or None if unavailable/failed."""
        raise NotImplementedError

class YFinanceFundamentalsProvider(BaseFundamentalsProvider):
    """Fetch fundamentals using yfinance ticker.info"""
    
    def fetch(self, symbol: str) -> Optional[Dict[str, Any]]:
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            info = ticker.info
            if not info:
                return None
            pe = info.get('trailingPE') or info.get('forwardPE')
            revenue_growth = info.get('revenueGrowth')
            profit_margins = info.get('profitMargins')
            market_cap = info.get('marketCap')
            sector = info.get('sector')
            industry = info.get('industry')
            # Sanitize and convert
            def to_float(val):
                if val is None:
                    return None
                try:
                    return float(val)
                except:
                    return None
            result = {
                'pe_ratio': to_float(pe),
                'revenue_growth_yoy': to_float(revenue_growth),
                'profit_margins': to_float(profit_margins),
                'market_cap': to_float(market_cap),
                'sector': sector,
                'industry': industry,
            }
            logger.debug(f"YFinance fundamentals for {symbol}: {result}")
            return result
        except Exception as e:
            logger.warning(f"YFinance fundamentals failed for {symbol}: {e}")
            return None

class AlphaVantageFundamentalsProvider(BaseFundamentalsProvider):
    """Fetch fundamentals using AlphaVantage API"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://www.alphavantage.co/query"
        # Rate limiting: free tier 5 calls/min
        self.min_interval = 12.0  # seconds between calls
        self._last_call = 0.0
    
    def _throttle(self):
        elapsed = time.time() - self._last_call
        if elapsed < self.min_interval:
            sleep_time = self.min_interval - elapsed
            logger.debug(f"AlphaVantage throttling: sleeping {sleep_time:.1f}s")
            time.sleep(sleep_time)
    
    def fetch(self, symbol: str) -> Optional[Dict[str, Any]]:
        try:
            import requests
            
            self._throttle()
            
            params = {
                "function": "OVERVIEW",
                "symbol": symbol,
                "apikey": self.api_key,
            }
            resp = requests.get(self.base_url, params=params, timeout=30)
            self._last_call = time.time()
            
            if resp.status_code != 200:
                logger.warning(f"AlphaVantage HTTP {resp.status_code} for {symbol}")
                return None
            
            data = resp.json()
            if "Error Message" in data or "Note" in data:
                logger.warning(f"AlphaVantage error for {symbol}: {data.get('Note') or data.get('Error Message')}")
                return None
            
            # Extract fields
            pe = data.get("PERatio") or data.get("PEGRatio")
            # PERatio is trailing PE
            revenue_growth = data.get("RevenueGrowthYTD") or data.get("QuarterlyRevenueGrowthYOY")
            profit_margins = data.get("ProfitMargin")
            market_cap = data.get("MarketCapitalization")
            sector = data.get("Sector")
            industry = data.get("Industry")
            
            def to_float(val):
                if val in (None, "", "None"):
                    return None
                try:
                    return float(val)
                except:
                    return None
            
            result = {
                'pe_ratio': to_float(pe),
                'revenue_growth_yoy': to_float(revenue_growth),
                'profit_margins': to_float(profit_margins),
                'market_cap': to_float(market_cap),
                'sector': sector,
                'industry': industry,
            }
            logger.debug(f"AlphaVantage fundamentals for {symbol}: {result}")
            return result
        except Exception as e:
            logger.warning(f"AlphaVantage fundamentals failed for {symbol}: {e}")
            return None

class OpenBBFundamentalsProvider(BaseFundamentalsProvider):
    """Fetch fundamentals using OpenBB platform (uses Yahoo, FMP, etc.)"""
    
    def fetch(self, symbol: str) -> Optional[Dict[str, Any]]:
        try:
            from openbb import obb
            # Use OpenBB's equity/overview or fundamentals
            # obb.equity.fundamental(symbol=symbol, provider='yahoo')? 
            # Actually the OpenBB Python API varies by version. We'll use a simple approach:
            # Try to get company overview
            response = obb.equity.fundamental(symbol=symbol, provider='yahoo')
            if response and hasattr(response, 'results'):
                # Structure depends on provider; we'll map
                # This is a placeholder; actual implementation may need adjustment
                return None
            return None
        except Exception as e:
            logger.warning(f"OpenBB fundamentals failed for {symbol}: {e}")
            return None

class FundamentalsFetcher:
    """Fetches fundamentals using a chain of providers with fallback."""
    
    def __init__(self, providers: list, alphavantage_api_key: Optional[str] = None):
        self.providers = []
        for name in providers:
            if name == "yfinance":
                self.providers.append(YFinanceFundamentalsProvider())
            elif name == "alphavantage":
                if not alphavantage_api_key:
                    logger.warning("AlphaVantage provider requested but no API key configured; skipping")
                    continue
                self.providers.append(AlphaVantageFundamentalsProvider(alphavantage_api_key))
            elif name == "openbb":
                try:
                    self.providers.append(OpenBBFundamentalsProvider())
                except Exception as e:
                    logger.warning(f"Failed to initialize OpenBB provider: {e}")
            else:
                logger.warning(f"Unknown fundamentals provider: {name}")
    
    def fetch(self, symbol: str) -> Dict[str, Any]:
        """Fetch fundamentals from the first provider that succeeds. Returns empty dict if all fail."""
        for provider in self.providers:
            try:
                result = provider.fetch(symbol)
                if result is not None:
                    return result
            except Exception as e:
                logger.warning(f"Provider {provider.__class__.__name__} raised: {e}")
                continue
        logger.warning(f"All fundamentals providers failed for {symbol}; returning empty dict")
        return {}
