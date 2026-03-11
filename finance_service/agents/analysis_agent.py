import logging
import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional
from finance_service.agents.agent_interface import Agent, AgentReport
from finance_service.core.events import Event, Events, get_event_bus
from finance_service.indicators.models import IndicatorResult, IndicatorsSnapshot, SignalType

logger = logging.getLogger(__name__)


class AnalysisAgent(Agent):
    """Analysis Agent - Computes technical indicators and transforms data into actionable signals."""

    @property
    def agent_id(self) -> str:
        return "analysis_agent"

    @property
    def goal(self) -> str:
        return "Transform raw market data into actionable technical analysis signals."

    def __init__(self, periods_config: Dict = None):
        self.periods = periods_config or self._default_periods()
        self.event_bus = get_event_bus()
        logger.info(f"AnalysisAgent initialized with periods: {self.periods}")

    @staticmethod
    def _default_periods():
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

    async def run(self, data_payload: Dict[str, Any], symbol: str) -> Optional[AgentReport]:
        """
        Calculates all configured indicators for a given symbol using a DataFrame reconstructed from data_payload.
        """
        logger.info(f"AnalysisAgent run: Calculating indicators for {symbol}")
        
        try:
            # Reconstruct DataFrame from the data_payload
            df = pd.DataFrame.from_dict(data_payload)
            # Ensure the index is datetime if it was originally so. Assuming 'Date' is the index name.
            if 'Date' in df.columns:
                df.set_index('Date', inplace=True)
            df.index = pd.to_datetime(df.index)
            
            snapshot = self._calculate_all(df, symbol)
            message = f"Indicators calculated for {symbol} at {snapshot.timestamp.isoformat()}"
            payload = snapshot.model_dump() # Convert Pydantic model to dict
            
            self.event_bus.publish(Event(
                event_type=Events.ANALYSIS_COMPLETE,
                data=payload
            ))
            
            return AgentReport(
                agent_id=self.agent_id,
                status="success",
                message=message,
                payload=payload
            )
        except ValueError as e:
            logger.warning(f"AnalysisAgent failed for {symbol}: {e}")
            # Publish ANALYSIS_FAILED event
            self.event_bus.publish(Event(
                event_type=Events.ANALYSIS_FAILED,
                data={"symbol": symbol, "reason": str(e)}
            ))
            return AgentReport(
                agent_id=self.agent_id,
                status="failure",
                message=f"Failed to calculate indicators for {symbol}: {e}"
            )
        except Exception as e:
            logger.error(f"Unexpected error in AnalysisAgent for {symbol}: {e}")
            # Publish ANALYSIS_FAILED event
            self.event_bus.publish(Event(
                event_type=Events.ANALYSIS_FAILED,
                data={"symbol": symbol, "reason": str(e)}
            ))
            return AgentReport(
                agent_id=self.agent_id,
                status="error",
                message=f"Unexpected error during analysis for {symbol}: {e}"
            )

    def _calculate_all(self, df: pd.DataFrame, symbol: str) -> IndicatorsSnapshot:
        """
        Calculate all indicators for a symbol
        
        Args:
            df: OHLCV DataFrame with datetime index
            symbol: Symbol name
        
        Returns:
            IndicatorsSnapshot with all indicators calculated
        
        Raises:
            ValueError: If insufficient data
        """
        # Validate input
        self._validate_ohlcv(df)
        
        if len(df) < 50:
            raise ValueError(f"Insufficient data: {len(df)} rows, need 50+")
        
        indicators = {}
        latest_ts = df.index[-1]
        
        try:
            # Calculate each indicator
            indicators['rsi'] = self.rsi(df)
            indicators['macd'] = self.macd(df)
            indicators['sma_20'] = self.sma(df, 20)
            indicators['sma_50'] = self.sma(df, 50)
            indicators['ema_12'] = self.ema(df, 12)
            indicators['ema_26'] = self.ema(df, 26)
            indicators['atr'] = self.atr(df)
            indicators['bb'] = self.bollinger_bands(df)
            indicators['stoch'] = self.stochastic(df)
            
            logger.debug(f"Calculated {len(indicators)} indicators for {symbol} at {latest_ts}")
            
            return IndicatorsSnapshot(
                symbol=symbol,
                timestamp=latest_ts,
                indicators=indicators
            )
        except Exception as e:
            logger.error(f"Error calculating indicators for {symbol}: {e}")
            raise
    
    def rsi(self, df: pd.DataFrame, period: int = 14) -> IndicatorResult:
        """
        Relative Strength Index (RSI)
        
        Formula:
            RSI = 100 - (100 / (1 + RS))
            RS = avg_gain / avg_loss
        
        Signal:
            RSI < 30: BUY (oversold)
            RSI > 70: SELL (overbought)
            30-70: HOLD
        """
        if len(df) < period + 1:
            raise ValueError(f"Need {period + 1}+ rows for RSI, got {len(df)}")
        
        # Calculate price changes
        delta = df['close'].diff()
        
        # Separate gains and losses
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        
        # Calculate average gain and loss
        avg_gain = gain.rolling(window=period, min_periods=period).mean()
        avg_loss = loss.rolling(window=period, min_periods=period).mean()
        
        # Handle zero loss case
        with np.errstate(divide='ignore', invalid='ignore'):
            rs = avg_gain / avg_loss
            rsi_values = 100 - (100 / (1 + rs))
        
        # Fill NaN with 50 (neutral)
        rsi_values = rsi_values.fillna(50)
        rsi = float(rsi_values.iloc[-1])
        
        # Generate signal
        if rsi < 30:
            signal = SignalType.BUY
        elif rsi > 70:
            signal = SignalType.SELL
        else:
            signal = SignalType.HOLD
        
        return IndicatorResult(
            name='rsi',
            value=float(rsi),
            signal=signal,
            timestamp=df.index[-1],
            metadata={'period': period, 'value': float(rsi)}
        )
    
    def macd(self, df: pd.DataFrame) -> IndicatorResult:
        """
        MACD (Moving Average Convergence Divergence)
        
        Formula:
            MACD = EMA12 - EMA26
            Signal = EMA9(MACD)
            Histogram = MACD - Signal
        
        Signal:
            Histogram > 0 and crossing above: BUY
            Histogram < 0 and crossing below: SELL
            Else: HOLD
        """
        if len(df) < 30:
            raise ValueError(f"Need 30+ rows for MACD, got {len(df)}")
        
        # Calculate EMAs
        ema12 = df['close'].ewm(span=12, adjust=False).mean()
        ema26 = df['close'].ewm(span=26, adjust=False).mean()
        
        # Calculate MACD line and signal line
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        histogram = macd_line - signal_line
        
        # Get current and previous values
        current_macd = float(macd_line.iloc[-1])
        current_signal = float(signal_line.iloc[-1])
        current_hist = float(histogram.iloc[-1])
        prev_hist = float(histogram.iloc[-2]) if len(histogram) > 1 else 0
        
        # Generate signal based on histogram
        if current_hist > 0 and prev_hist <= 0:
            signal = SignalType.BUY  # Bullish crossover
        elif current_hist < 0 and prev_hist >= 0:
            signal = SignalType.SELL  # Bearish crossover
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
        """
        Simple Moving Average (SMA)
        
        Formula:
            SMA = sum(close, period) / period
        
        Signal:
            Price > SMA * 1.01: BUY
            Price < SMA * 0.99: SELL
            Else: HOLD
        """
        if len(df) < period:
            raise ValueError(f"Need {period}+ rows for SMA({period}), got {len(df)}")
        
        # Calculate SMA
        sma_values = df['close'].rolling(window=period, min_periods=period).mean()
        sma = float(sma_values.iloc[-1])
        current_price = float(df['close'].iloc[-1])
        
        # Generate signal based on price vs SMA
        if pd.isna(sma):
            signal = SignalType.HOLD
        elif current_price > sma * 1.01:  # 1% above
            signal = SignalType.BUY
        elif current_price < sma * 0.99:  # 1% below
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
        """
        Exponential Moving Average (EMA)
        
        Formula:
            EMA = close * multiplier + EMA_prev * (1 - multiplier)
            multiplier = 2 / (period + 1)
        
        Signal:
            Price > EMA * 1.01: BUY
            Price < EMA * 0.99: SELL
            Else: HOLD
        """
        if len(df) < period:
            raise ValueError(f"Need {period}+ rows for EMA({period}), got {len(df)}")
        
        # Calculate EMA
        ema_values = df['close'].ewm(span=period, adjust=False).mean()
        ema = float(ema_values.iloc[-1])
        current_price = float(df['close'].iloc[-1])
        
        # Generate signal based on price vs EMA
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
        """
        Average True Range (ATR)
        
        Formula:
            TR = max(H-L, abs(H-PC), abs(L-PC))
            ATR = EMA(TR, period)
        
        Used for: Stop loss and take profit sizing
        Signal: HOLD (ATR is not a directional indicator)
        """
        if len(df) < period + 1:
            raise ValueError(f"Need {period + 1}+ rows for ATR, got {len(df)}")
        
        high = df['high']
        low = df['low']
        close = df['close']
        
        # Calculate True Range
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        # Calculate ATR (EMA of TR)
        atr_values = tr.ewm(span=period, adjust=False).mean()
        atr = float(atr_values.iloc[-1])
        
        if pd.isna(atr):
            atr = float(tr.iloc[-period:].mean())
        
        return IndicatorResult(
            name='atr',
            value=atr,
            signal=SignalType.HOLD,  # ATR not a directional signal
            timestamp=df.index[-1],
            metadata={'period': period, 'atr': atr}
        )
    
    def bollinger_bands(self, df: pd.DataFrame, period: int = 20, std: float = 2.0) -> IndicatorResult:
        """
        Bollinger Bands
        
        Formula:
            Middle = SMA(close, period)
            Std = StdDev(close, period)
            Upper = Middle + (std * Std)
            Lower = Middle - (std * Std)
        
        Signal:
            Price > Upper: SELL (overbought)
            Price < Lower: BUY (oversold)
            Else: HOLD
        """
        if len(df) < period:
            raise ValueError(f"Need {period}+ rows for Bollinger Bands, got {len(df)}")
        
        # Calculate SMA and standard deviation
        sma = df['close'].rolling(window=period, min_periods=period).mean()
        std_dev = df['close'].rolling(window=period, min_periods=period).std()
        
        # Calculate bands
        upper_band = sma + (std * std_dev)
        lower_band = sma - (std * std_dev)
        
        # Get current values
        current_price = float(df['close'].iloc[-1])
        current_upper = float(upper_band.iloc[-1])
        current_lower = float(lower_band.iloc[-1])
        current_sma = float(sma.iloc[-1])
        
        # Generate signal
        if pd.isna(current_upper) or pd.isna(current_lower):
            signal = SignalType.HOLD
        elif current_price > current_upper * 0.99:  # Touch upper band
            signal = SignalType.SELL
        elif current_price < current_lower * 1.01:  # Touch lower band
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
        """
        Stochastic Oscillator
        
        Formula:
            %K = 100 * (Close - LowestLow) / (HighestHigh - LowestLow)
            %D = SMA(%K, d_period)
        
        Signal:
            %K < 20: BUY (oversold)
            %K > 80: SELL (overbought)
            %K crosses above %D: BUY
            %K crosses below %D: SELL
            Else: HOLD
        """
        if len(df) < k_period:
            raise ValueError(f"Need {k_period}+ rows for Stochastic, got {len(df)}")
        
        # Calculate highest high and lowest low
        high_high = df['high'].rolling(window=k_period, min_periods=k_period).max()
        low_low = df['low'].rolling(window=k_period, min_periods=k_period).min()
        
        # Calculate %K
        denominator = high_high - low_low
        # Avoid division by zero
        with np.errstate(divide='ignore', invalid='ignore'):
            k_percent = 100 * ((df['close'] - low_low) / denominator)
        
        k_percent = k_percent.fillna(50)  # Fill NaN with 50 (neutral)
        
        # Calculate %D (SMA of %K)
        d_percent = k_percent.rolling(window=d_period, min_periods=d_period).mean()
        d_percent = d_percent.fillna(50)
        
        # Get current and previous values
        current_k = float(k_percent.iloc[-1])
        current_d = float(d_percent.iloc[-1])
        prev_k = float(k_percent.iloc[-2]) if len(k_percent) > 1 else current_k
        prev_d = float(d_percent.iloc[-2]) if len(d_percent) > 1 else current_d
        
        # Generate signal
        if current_k < 20:
            signal = SignalType.BUY  # Oversold
        elif current_k > 80:
            signal = SignalType.SELL  # Overbought
        elif current_k > prev_k and current_k > current_d and prev_k <= prev_d:
            signal = SignalType.BUY  # K crosses above D
        elif current_k < prev_k and current_k < current_d and prev_k >= prev_d:
            signal = SignalType.SELL  # K crosses below D
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
        """
        Validate OHLCV DataFrame
        
        Checks:
            - Required columns present
            - No NaN values
            - At least 50 rows
        
        Raises:
            ValueError: If validation fails
        """
        required_cols = {'open', 'high', 'low', 'close', 'volume'}
        df_cols = set(df.columns)
        
        if not required_cols.issubset(df_cols):
            missing = required_cols - df_cols
            raise ValueError(f"Missing columns: {missing}. Need {required_cols}, got {df_cols}")
        
        # Check for NaN values
        if df[list(required_cols)].isnull().any().any():
            raise ValueError("Data contains NaN values in OHLCV columns")
        
        # Check minimum length
        if len(df) < 5:
            raise ValueError(f"Need at least 5 rows, got {len(df)}")
