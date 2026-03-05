"""OpenBB data retrieval tools"""
import pandas as pd
from typing import Dict, List, Optional, Any
import logging
from datetime import datetime, timedelta
from ..core.cache import Cache
from ..core.config import Config
import os

logger = logging.getLogger(__name__)

# Force OpenBB to use yfinance provider before import
os.environ['OPENBB_USE_YFINANCE'] = 'true'
os.environ['OPENBB_PROVIDER'] = 'yfinance'

class OpenBBTools:
    """Wrapper around OpenBB SDK for market data"""
    
    def __init__(self):
        self.cache = Cache()
        try:
            from openbb import obb
            self.obb = obb
        except ImportError:
            logger.warning("OpenBB not installed. Using mock data mode.")
            self.obb = None
    
    def get_price_historical(self, symbol: str, start_date: Optional[str] = None,
                            end_date: Optional[str] = None, 
                            interval: str = "1day") -> Dict[str, Any]:
        """
        Fetch historical prices from OpenBB
        
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
            if not self.obb:
                return self._mock_price_data(symbol)
            
            # Convert interval format to OpenBB format (1day -> 1d)
            interval_map = {"1day": "1d", "1d": "1d", "1h": "1h", "5m": "5m"}
            normalized_interval = interval_map.get(interval, "1d")
            
            data = self.obb.equity.price.historical(
                symbol=symbol.upper(),
                start_date=start_date,
                end_date=end_date,
                interval=normalized_interval
            )
            
            # Convert OBBobject results to DataFrame
            if hasattr(data, 'results') and isinstance(data.results, list):
                # OBB returns a list of YFinanceEquityHistoricalData objects
                df = pd.DataFrame([
                    {
                        'date': r.date if hasattr(r, 'date') else r.get('date'),
                        'open': float(r.open) if hasattr(r, 'open') else float(r.get('open', 0)),
                        'high': float(r.high) if hasattr(r, 'high') else float(r.get('high', 0)),
                        'low': float(r.low) if hasattr(r, 'low') else float(r.get('low', 0)),
                        'close': float(r.close) if hasattr(r, 'close') else float(r.get('close', 0)),
                        'volume': float(r.volume) if hasattr(r, 'volume') else float(r.get('volume', 0)),
                    }
                    for r in data.results
                ])
                df['date'] = pd.to_datetime(df['date'])
                df.set_index('date', inplace=True)
            else:
                return {"error": "Unexpected data format from OBB"}
            
            if df.empty:
                logger.warning(f"No data returned for {symbol}")
                return {"error": "No data available"}
            
            # Extract OHLCV data
            result = {
                "symbol": symbol.upper(),
                "dates": df.index.strftime("%Y-%m-%d").tolist(),
                "open": df["open"].tolist(),
                "high": df["high"].tolist(),
                "low": df["low"].tolist(),
                "close": df["close"].tolist(),
                "volume": df["volume"].tolist(),
            }
            
            self.cache.set(cache_key, result, ttl_seconds=3600)
            logger.info(f"Fetched {len(df)} rows for {symbol}")
            return result
        
        except Exception as e:
            logger.error(f"Error fetching price data for {symbol}: {str(e)}")
            return {"error": str(e), "symbol": symbol}
    
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
            if not self.obb:
                return self._mock_fundamentals(symbol, statement_type)
            
            if statement_type == "income":
                data = self.obb.equity.fundamental.income(symbol=symbol.upper())
            elif statement_type == "balance":
                data = self.obb.equity.fundamental.balance(symbol=symbol.upper())
            elif statement_type == "cashflow":
                data = self.obb.equity.fundamental.cash_flow(symbol=symbol.upper())
            else:
                return {"error": f"Unknown statement type: {statement_type}"}
            
            result = {
                "symbol": symbol.upper(),
                "statement_type": statement_type,
                "data": data.to_dict() if hasattr(data, 'to_dict') else str(data),
            }
            
            self.cache.set(cache_key, result, ttl_seconds=86400)  # 24 hours
            return result
        
        except Exception as e:
            logger.error(f"Error fetching fundamentals for {symbol}: {str(e)}")
            return {"error": str(e), "symbol": symbol}
    
    def get_company_profile(self, symbol: str) -> Dict[str, Any]:
        """Get company profile and key metrics"""
        cache_key = f"profile_{symbol}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached
        
        try:
            if not self.obb:
                return self._mock_profile(symbol)
            
            data = self.obb.equity.profile(symbol=symbol.upper())
            
            result = {
                "symbol": symbol.upper(),
                "data": data.to_dict() if hasattr(data, 'to_dict') else str(data),
            }
            
            self.cache.set(cache_key, result, ttl_seconds=86400)
            return result
        
        except Exception as e:
            logger.error(f"Error fetching profile for {symbol}: {str(e)}")
            return {"error": str(e), "symbol": symbol}
    
    def get_quote(self, symbol: str) -> Dict[str, Any]:
        """Get latest quote"""
        cache_key = f"quote_{symbol}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached
        
        try:
            if not self.obb:
                return self._mock_quote(symbol)
            
            data = self.obb.equity.quote(symbol=symbol.upper())
            result = {
                "symbol": symbol.upper(),
                "price": float(data.get("price", 0)) if data else 0,
                "data": data.to_dict() if hasattr(data, 'to_dict') else dict(data) if data else {},
            }
            
            self.cache.set(cache_key, result, ttl_seconds=300)  # 5 min cache
            return result
        
        except Exception as e:
            logger.error(f"Error fetching quote for {symbol}: {str(e)}")
            return {"error": str(e), "symbol": symbol}
    
    @staticmethod
    def _mock_price_data(symbol: str) -> Dict[str, Any]:
        """Mock price data for testing"""
        import numpy as np
        dates = pd.date_range(end=datetime.now(), periods=100, freq='D')
        np.random.seed(hash(symbol) % 2**32)
        prices = 100 + np.cumsum(np.random.randn(100) * 2)
        
        return {
            "symbol": symbol.upper(),
            "dates": dates.strftime("%Y-%m-%d").tolist(),
            "open": (prices * 0.99).tolist(),
            "high": (prices * 1.01).tolist(),
            "low": (prices * 0.98).tolist(),
            "close": prices.tolist(),
            "volume": (np.random.rand(100) * 1000000).astype(int).tolist(),
        }
    
    @staticmethod
    def _mock_fundamentals(symbol: str, statement_type: str) -> Dict[str, Any]:
        """Mock fundamental data"""
        return {
            "symbol": symbol.upper(),
            "statement_type": statement_type,
            "data": {
                "revenue": 1000000000,
                "net_income": 200000000,
                "eps": 5.0,
            }
        }
    
    @staticmethod
    def _mock_profile(symbol: str) -> Dict[str, Any]:
        """Mock company profile"""
        return {
            "symbol": symbol.upper(),
            "data": {
                "name": f"{symbol} Inc",
                "sector": "Technology",
                "industry": "Software",
            }
        }
    
    @staticmethod
    def _mock_quote(symbol: str) -> Dict[str, Any]:
        """Mock quote data"""
        import random
        random.seed(hash(symbol) % 2**32)
        price = 100 + random.gauss(0, 5)
        
        return {
            "symbol": symbol.upper(),
            "price": price,
            "data": {
                "price": price,
                "bid": price - 0.01,
                "ask": price + 0.01,
            }
        }
