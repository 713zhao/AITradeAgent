"""Technical indicator calculator - standalone class for testing and reuse"""
import pandas as pd
import numpy as np
from typing import Dict, Any
from datetime import datetime

from finance_service.indicators.models import IndicatorResult, IndicatorsSnapshot, SignalType


class IndicatorCalculator:
    """Calculate technical indicators from OHLCV data."""
    
    def __init__(self, periods: Dict[str, Any] = None):
        """Initialize with indicator periods."""
        self.periods = periods or self._default_periods()
    
    def _default_periods(self) -> Dict[str, Any]:
        """Default indicator periods"""
        return {
            'rsi': 14,
            'macd_fast': 12,
            'macd_slow': 26,
            'macd_signal': 9,
            'sma': [20, 50],
            'ema': [12, 26],
            'atr': 14,
            'bb_period': 20,
            'bb_std': 2.0,
            'stoch_k': 14,
            'stoch_d': 3,
        }
    
    def calculate_all(self, df: pd.DataFrame, symbol: str) -> IndicatorsSnapshot:
        """
        Calculate all configured indicators for a DataFrame.
        
        Args:
            df: OHLCV DataFrame with datetime index
            symbol: Symbol name
            
        Returns:
            IndicatorsSnapshot with all indicators
            
        Raises:
            ValueError: If insufficient data
        """
        self._validate_ohlcv(df)
        
        if len(df) < 50:
            raise ValueError(f"Insufficient data: {len(df)} rows, need 50+")
        
        indicators = {}
        latest_ts = df.index[-1]
        
        try:
            indicators['rsi'] = self.rsi(df)
            indicators['macd'] = self.macd(df)
            indicators['sma_20'] = self.sma(df, 20)
            indicators['sma_50'] = self.sma(df, 50)
            indicators['ema_12'] = self.ema(df, 12)
            indicators['ema_26'] = self.ema(df, 26)
            indicators['atr'] = self.atr(df)
            indicators['bb'] = self.bollinger_bands(df)
            indicators['stoch'] = self.stochastic(df)
            
            return IndicatorsSnapshot(
                symbol=symbol,
                timestamp=latest_ts,
                indicators=indicators
            )
        except Exception as e:
            raise
    
    def rsi(self, df: pd.DataFrame, period: int = 14) -> IndicatorResult:
        """Relative Strength Index"""
        if len(df) < period + 1:
            raise ValueError(f"Need {period + 1}+ rows for RSI, got {len(df)}")
        
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        
        avg_gain = gain.rolling(window=period, min_periods=period).mean()
        avg_loss = loss.rolling(window=period, min_periods=period).mean()
        
        with np.errstate(divide='ignore', invalid='ignore'):
            rs = avg_gain / avg_loss
            rsi_values = 100 - (100 / (1 + rs))
        
        rsi_values = rsi_values.fillna(50)
        rsi = float(rsi_values.iloc[-1])
        
        # Signal
        if rsi < 30:
            signal = SignalType.BUY
        elif rsi > 70:
            signal = SignalType.SELL
        else:
            signal = SignalType.HOLD
        
        return IndicatorResult(
            name='rsi',
            value=rsi,
            signal=signal,
            timestamp=df.index[-1],
            metadata={'period': period, 'value': rsi}
        )
    
    def macd(self, df: pd.DataFrame) -> IndicatorResult:
        """MACD (Moving Average Convergence Divergence)"""
        if len(df) < 30:
            raise ValueError(f"Need 30+ rows for MACD, got {len(df)}")
        
        ema12 = df['close'].ewm(span=12, adjust=False).mean()
        ema26 = df['close'].ewm(span=26, adjust=False).mean()
        
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        histogram = macd_line - signal_line
        
        current_macd = float(macd_line.iloc[-1])
        current_signal = float(signal_line.iloc[-1])
        current_hist = float(histogram.iloc[-1])
        prev_hist = float(histogram.iloc[-2]) if len(histogram) > 1 else 0
        
        # Signal based on histogram crossover
        if current_hist > 0 and prev_hist <= 0:
            signal = SignalType.BUY
        elif current_hist < 0 and prev_hist >= 0:
            signal = SignalType.SELL
        else:
            signal = SignalType.HOLD
        
        return IndicatorResult(
            name='macd',
            value=current_macd,
            signal=signal,
            timestamp=df.index[-1],
            metadata={
                'macd_line': current_macd,
                'signal_line': current_signal,
                'histogram': current_hist
            }
        )
    
    def sma(self, df: pd.DataFrame, period: int = 20) -> IndicatorResult:
        """Simple Moving Average"""
        if len(df) < period:
            raise ValueError(f"Need {period}+ rows for SMA({period}), got {len(df)}")
        
        sma_values = df['close'].rolling(window=period, min_periods=period).mean()
        sma = float(sma_values.iloc[-1])
        current_price = float(df['close'].iloc[-1])
        
        # Signal based on price vs SMA
        if pd.isna(sma):
            signal = SignalType.HOLD
        elif current_price > sma * 1.01:
            signal = SignalType.BUY
        elif current_price < sma * 0.99:
            signal = SignalType.SELL
        else:
            signal = SignalType.HOLD
        
        return IndicatorResult(
            name=f'sma_{period}',
            value=sma,
            signal=signal,
            timestamp=df.index[-1],
            metadata={'period': period, 'price': current_price, 'sma': sma}
        )
    
    def ema(self, df: pd.DataFrame, period: int = 12) -> IndicatorResult:
        """Exponential Moving Average"""
        if len(df) < period:
            raise ValueError(f"Need {period}+ rows for EMA({period}), got {len(df)}")
        
        ema_values = df['close'].ewm(span=period, adjust=False).mean()
        ema = float(ema_values.iloc[-1])
        current_price = float(df['close'].iloc[-1])
        
        if pd.isna(ema):
            signal = SignalType.HOLD
        elif current_price > ema * 1.01:
            signal = SignalType.BUY
        elif current_price < ema * 0.99:
            signal = SignalType.SELL
        else:
            signal = SignalType.HOLD
        
        return IndicatorResult(
            name=f'ema_{period}',
            value=ema,
            signal=signal,
            timestamp=df.index[-1],
            metadata={'period': period, 'price': current_price, 'ema': ema}
        )
    
    def atr(self, df: pd.DataFrame, period: int = 14) -> IndicatorResult:
        """Average True Range"""
        if len(df) < period + 1:
            raise ValueError(f"Need {period + 1}+ rows for ATR, got {len(df)}")
        
        high = df['high']
        low = df['low']
        close = df['close']
        
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr_values = tr.ewm(span=period, adjust=False).mean()
        atr = float(atr_values.iloc[-1])
        
        if pd.isna(atr):
            atr = float(tr.iloc[-period:].mean())
        
        return IndicatorResult(
            name='atr',
            value=atr,
            signal=SignalType.HOLD,
            timestamp=df.index[-1],
            metadata={'period': period, 'atr': atr}
        )
    
    def bollinger_bands(self, df: pd.DataFrame, period: int = 20, std: float = 2.0) -> IndicatorResult:
        """Bollinger Bands"""
        if len(df) < period:
            raise ValueError(f"Need {period}+ rows for Bollinger Bands, got {len(df)}")
        
        sma = df['close'].rolling(window=period, min_periods=period).mean()
        std_dev = df['close'].rolling(window=period, min_periods=period).std()
        
        upper_band = sma + (std * std_dev)
        lower_band = sma - (std * std_dev)
        
        current_price = float(df['close'].iloc[-1])
        current_upper = float(upper_band.iloc[-1])
        current_lower = float(lower_band.iloc[-1])
        current_sma = float(sma.iloc[-1])
        
        if pd.isna(current_upper) or pd.isna(current_lower):
            signal = SignalType.HOLD
        elif current_price > current_upper * 0.99:
            signal = SignalType.SELL
        elif current_price < current_lower * 1.01:
            signal = SignalType.BUY
        else:
            signal = SignalType.HOLD
        
        return IndicatorResult(
            name='bb',
            value=current_sma,
            signal=signal,
            timestamp=df.index[-1],
            metadata={
                'period': period,
                'std': std,
                'upper': current_upper,
                'middle': current_sma,
                'lower': current_lower,
                'price': current_price
            }
        )
    
    def stochastic(self, df: pd.DataFrame, k_period: int = 14, d_period: int = 3) -> IndicatorResult:
        """Stochastic Oscillator"""
        if len(df) < k_period:
            raise ValueError(f"Need {k_period}+ rows for Stochastic, got {len(df)}")
        
        high_high = df['high'].rolling(window=k_period, min_periods=k_period).max()
        low_low = df['low'].rolling(window=k_period, min_periods=k_period).min()
        
        denominator = high_high - low_low
        with np.errstate(divide='ignore', invalid='ignore'):
            k_percent = 100 * ((df['close'] - low_low) / denominator)
        
        k_percent = k_percent.fillna(50)
        d_percent = k_percent.rolling(window=d_period, min_periods=d_period).mean()
        d_percent = d_percent.fillna(50)
        
        current_k = float(k_percent.iloc[-1])
        current_d = float(d_percent.iloc[-1])
        prev_k = float(k_percent.iloc[-2]) if len(k_percent) > 1 else current_k
        prev_d = float(d_percent.iloc[-2]) if len(d_percent) > 1 else current_d
        
        # Signal
        if current_k < 20:
            signal = SignalType.BUY
        elif current_k > 80:
            signal = SignalType.SELL
        elif current_k > prev_k and current_k > current_d and prev_k <= prev_d:
            signal = SignalType.BUY
        elif current_k < prev_k and current_k < current_d and prev_k >= prev_d:
            signal = SignalType.SELL
        else:
            signal = SignalType.HOLD
        
        return IndicatorResult(
            name='stoch',
            value=current_k,
            signal=signal,
            timestamp=df.index[-1],
            metadata={
                'k_period': k_period,
                'd_period': d_period,
                'k_percent': current_k,
                'd_percent': current_d
            }
        )
    
    @staticmethod
    def _validate_ohlcv(df: pd.DataFrame) -> None:
        """Validate OHLCV DataFrame"""
        required_cols = {'open', 'high', 'low', 'close', 'volume'}
        df_cols = set(df.columns)
        
        if not required_cols.issubset(df_cols):
            missing = required_cols - df_cols
            raise ValueError(f"Missing columns: {missing}. Need {required_cols}, got {df_cols}")
        
        if df[list(required_cols)].isnull().any().any():
            raise ValueError("Data contains NaN values in OHLCV columns")
        
        if len(df) < 5:
            raise ValueError(f"Need at least 5 rows, got {len(df)}")
