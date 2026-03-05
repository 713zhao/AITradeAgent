"""Technical indicator calculation tools"""
import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
import logging

logger = logging.getLogger(__name__)

class IndicatorTools:
    """Calculate technical indicators from OHLCV data"""
    
    @staticmethod
    def calc_rsi(prices: List[float], period: int = 14) -> List[float]:
        """
        Calculate Relative Strength Index
        
        Args:
            prices: List of closing prices
            period: Window period (default 14)
        
        Returns:
            List of RSI values
        """
        if len(prices) < period + 1:
            return []
        
        prices = np.array(prices, dtype=float)
        deltas = np.diff(prices)
        seed = deltas[:period + 1]
        
        up = seed[seed >= 0].sum() / period
        down = -seed[seed < 0].sum() / period
        
        rs = up / down if down != 0 else 0
        rsi = np.zeros_like(prices)
        rsi[:period] = 100.0 - 100.0 / (1.0 + rs)
        
        for i in range(period, len(prices)):
            delta = deltas[i - 1]
            
            if delta > 0:
                upval = delta
                downval = 0.0
            else:
                upval = 0.0
                downval = -delta
            
            up = (up * (period - 1) + upval) / period
            down = (down * (period - 1) + downval) / period
            
            rs = up / down if down != 0 else 0
            rsi[i] = 100.0 - 100.0 / (1.0 + rs)
        
        return rsi[period:].tolist()
    
    @staticmethod
    def calc_macd(prices: List[float], fast: int = 12, slow: int = 26, 
                  signal: int = 9) -> Dict[str, List[float]]:
        """
        Calculate MACD (Moving Average Convergence Divergence)
        
        Args:
            prices: List of closing prices
            fast: Fast EMA period (default 12)
            slow: Slow EMA period (default 26)
            signal: Signal line period (default 9)
        
        Returns:
            dict with 'macd', 'signal', 'histogram'
        """
        prices = np.array(prices, dtype=float)
        
        # Calculate EMAs
        ema_fast = IndicatorTools._calc_ema(prices, fast)
        ema_slow = IndicatorTools._calc_ema(prices, slow)
        
        # MACD line
        macd_line = ema_fast - ema_slow
        
        # Signal line
        signal_line = IndicatorTools._calc_ema(macd_line, signal)
        
        # Histogram
        histogram = macd_line - signal_line
        
        return {
            "macd": macd_line.tolist(),
            "signal": signal_line.tolist(),
            "histogram": histogram.tolist(),
        }
    
    @staticmethod
    def calc_sma(prices: List[float], window: int = 20) -> List[float]:
        """
        Calculate Simple Moving Average
        
        Args:
            prices: List of closing prices
            window: Moving average window
        
        Returns:
            List of SMA values
        """
        prices = np.array(prices, dtype=float)
        return np.convolve(prices, np.ones(window) / window, mode='valid').tolist()
    
    @staticmethod
    def calc_ema(prices: List[float], window: int = 20) -> List[float]:
        """Calculate Exponential Moving Average"""
        prices = np.array(prices, dtype=float)
        return IndicatorTools._calc_ema(prices, window).tolist()
    
    @staticmethod
    def _calc_ema(prices: np.ndarray, window: int) -> np.ndarray:
        """Internal EMA calculation"""
        if len(prices) < window:
            return np.array([])
        
        ema = np.zeros_like(prices)
        ema[window - 1] = prices[:window].mean()
        
        multiplier = 2.0 / (window + 1)
        for i in range(window, len(prices)):
            ema[i] = (prices[i] * multiplier) + (ema[i - 1] * (1 - multiplier))
        
        return ema[window - 1:]
    
    @staticmethod
    def calc_atr(highs: List[float], lows: List[float], closes: List[float], 
                 period: int = 14) -> List[float]:
        """
        Calculate Average True Range
        
        Args:
            highs: List of high prices
            lows: List of low prices
            closes: List of closing prices
            period: ATR period (default 14)
        
        Returns:
            List of ATR values
        """
        highs = np.array(highs, dtype=float)
        lows = np.array(lows, dtype=float)
        closes = np.array(closes, dtype=float)
        
        # Calculate true range
        tr1 = highs - lows
        # Handle previous close: pad with first close value for the first bar
        prev_closes = np.concatenate([[closes[0]], closes[:-1]])
        tr2 = np.abs(highs - prev_closes)
        tr3 = np.abs(lows - prev_closes)
        
        tr = np.maximum(np.maximum(tr1, tr2), tr3)
        
        # Calculate ATR
        atr = np.zeros_like(tr)
        atr[period - 1] = tr[:period].mean()
        
        for i in range(period, len(tr)):
            atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
        
        return atr[period - 1:].tolist()
    
    @staticmethod
    def calc_bollinger_bands(prices: List[float], window: int = 20, 
                            num_std: float = 2) -> Dict[str, List[float]]:
        """
        Calculate Bollinger Bands
        
        Args:
            prices: List of closing prices
            window: Moving average period
            num_std: Number of standard deviations
        
        Returns:
            dict with 'upper', 'middle', 'lower'
        """
        prices = np.array(prices, dtype=float)
        middle = np.convolve(prices, np.ones(window) / window, mode='valid')
        std = np.std(prices[-len(middle)-window+1:]) if len(prices) >= window else 0
        
        upper = middle + (num_std * std)
        lower = middle - (num_std * std)
        
        return {
            "upper": upper.tolist(),
            "middle": middle.tolist(),
            "lower": lower.tolist(),
        }
    
    @staticmethod
    def calc_stochastic(highs: List[float], lows: List[float], 
                       closes: List[float], k_period: int = 14, 
                       d_period: int = 3) -> Dict[str, List[float]]:
        """
        Calculate Stochastic Oscillator
        
        Args:
            highs: List of high prices
            lows: List of low prices
            closes: List of closing prices
            k_period: K% period
            d_period: D% period
        
        Returns:
            dict with 'k', 'd'
        """
        highs = np.array(highs, dtype=float)
        lows = np.array(lows, dtype=float)
        closes = np.array(closes, dtype=float)
        
        lowest_low = np.array([lows[max(0, i - k_period + 1):i + 1].min() 
                               for i in range(len(lows))])
        highest_high = np.array([highs[max(0, i - k_period + 1):i + 1].max() 
                                 for i in range(len(highs))])
        
        k_percent = 100 * (closes - lowest_low) / (highest_high - lowest_low + 1e-10)
        
        # D% is SMA of K%
        d_percent = np.convolve(k_percent, np.ones(d_period) / d_period, mode='valid')
        
        return {
            "k": k_percent[k_period - 1:].tolist(),
            "d": d_percent.tolist(),
        }
