"""Market data retrieval tools using yfinance"""
import pandas as pd
from typing import Dict, List, Optional, Any
import logging
from datetime import datetime, timedelta
from ..core.cache import Cache
from ..core.config import Config
import yfinance as yf

logger = logging.getLogger(__name__)

class OpenBBTools:
    """Wrapper around yfinance for market data"""
    
    def __init__(self):
        self.cache = Cache()
        self.yf = yf
    
    def get_price_historical(self, symbol: str, start_date: Optional[str] = None,
                            end_date: Optional[str] = None, 
                            interval: str = "1day") -> Dict[str, Any]:
        """
        Fetch historical prices from yfinance
        
        Args:
            symbol: Ticker symbol (e.g., "AAPL")
            start_date: ISO format date string
            end_date: ISO format date string
            interval: "1day", "1hour", etc.
        
        Returns:
            dict with keys: close, high, low, open, volume, dates
        """
        if not start_date:
            start_date = (datetime.now() - timedelta(days=Config.DEFAULT_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        
        cache_key = f"price_hist_{symbol}_{start_date}_{end_date}_{interval}"
        cached = self.cache.get(cache_key)
        if cached:
            logger.debug(f"Using cached data for {symbol}")
            return cached
        
        try:
            # Convert interval format (1day -> 1d, etc.)
            interval_map = {"1day": "1d", "1d": "1d", "1h": "1h", "5m": "5m"}
            normalized_interval = interval_map.get(interval, "1d")
            
            ticker = yf.Ticker(symbol.upper())
            data = ticker.history(start=start_date, end=end_date, interval=normalized_interval)
            
            if data.empty:
                return {"error": f"No data available for {symbol} from {start_date} to {end_date}"}
            
            result = {
                "symbol": symbol.upper(),
                "dates": data.index.strftime("%Y-%m-%d").tolist(),
                "open": data["Open"].tolist(),
                "high": data["High"].tolist(),
                "low": data["Low"].tolist(),
                "close": data["Close"].tolist(),
                "volume": data["Volume"].astype(int).tolist(),
            }
            
            self.cache.set(cache_key, result, ttl_seconds=3600)
            logger.info(f"Fetched {len(data)} rows for {symbol}")
            return result
        
        except Exception as e:
            error_msg = f"Error fetching price data for {symbol}: {str(e)}"
            logger.error(error_msg)
            return {"error": error_msg, "symbol": symbol}
    
    def get_fundamentals(self, symbol: str, statement_type: str = "income") -> Dict[str, Any]:
        """
        Fetch fundamental data
        
        Args:
            symbol: Ticker symbol
            statement_type: "income", "balance", "cashflow"
        
        Returns:
            dict with financial statement data
        """
        cache_key = f"fundamentals_{symbol}_{statement_type}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached
        
        try:
            ticker = yf.Ticker(symbol.upper())
            
            if statement_type == "income":
                data = ticker.quarterly_financials
            elif statement_type == "balance":
                data = ticker.quarterly_balance_sheet
            elif statement_type == "cashflow":
                data = ticker.quarterly_cashflow
            else:
                return {"error": f"Unknown statement type: {statement_type}"}
            
            if data is None or data.empty:
                return {"error": f"No {statement_type} data available for {symbol}"}
            
            result = {
                "symbol": symbol.upper(),
                "statement_type": statement_type,
                "data": data.to_dict() if hasattr(data, 'to_dict') else str(data),
            }
            
            self.cache.set(cache_key, result, ttl_seconds=86400)  # 24 hours
            return result
        
        except Exception as e:
            error_msg = f"Error fetching {statement_type} for {symbol}: {str(e)}"
            logger.error(error_msg)
            return {"error": error_msg, "symbol": symbol}
    
    def get_company_profile(self, symbol: str) -> Dict[str, Any]:
        """Get company profile and key metrics"""
        cache_key = f"profile_{symbol}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached
        
        try:
            ticker = yf.Ticker(symbol.upper())
            info = ticker.info
            
            if not info:
                return {"error": f"No profile data available for {symbol}"}
            
            result = {
                "symbol": symbol.upper(),
                "data": {
                    "name": info.get("longName", ""),
                    "sector": info.get("sector", ""),
                    "industry": info.get("industry", ""),
                    "market_cap": info.get("marketCap", 0),
                    "pe_ratio": info.get("trailingPE", 0),
                    "dividend_yield": info.get("dividendYield", 0),
                    "description": info.get("longBusinessSummary", ""),
                }
            }
            
            self.cache.set(cache_key, result, ttl_seconds=86400)
            return result
        
        except Exception as e:
            error_msg = f"Error fetching profile for {symbol}: {str(e)}"
            logger.error(error_msg)
            return {"error": error_msg, "symbol": symbol}
    
    def get_quote(self, symbol: str) -> Dict[str, Any]:
        """Get latest quote"""
        cache_key = f"quote_{symbol}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached
        
        try:
            ticker = yf.Ticker(symbol.upper())
            info = ticker.info
            
            if not info:
                return {"error": f"No quote data available for {symbol}"}
            
            result = {
                "symbol": symbol.upper(),
                "price": info.get("currentPrice", info.get("last_price", 0)),
                "data": {
                    "price": info.get("currentPrice", 0),
                    "bid": info.get("bid", 0),
                    "ask": info.get("ask", 0),
                    "volume": info.get("volume", 0),
                    "market_cap": info.get("marketCap", 0),
                    "timestamp": datetime.now().isoformat(),
                }
            }
            
            self.cache.set(cache_key, result, ttl_seconds=300)  # 5 min cache
            return result
        
        except Exception as e:
            error_msg = f"Error fetching quote for {symbol}: {str(e)}"
            logger.error(error_msg)
            return {"error": error_msg, "symbol": symbol}
