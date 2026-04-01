import logging
from finance_service.core.flow_logger import flow
import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional, Any
from finance_service.agents.agent_interface import Agent, AgentReport
from finance_service.core.event_bus import Event, Events, get_event_bus
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
        flow("AnalysisAgent", "START", f"{symbol}")
        
        try:
            # data_payload is the full Event.data from DATA_FETCH_COMPLETE
            # Extract the actual dataframe (list of records) and fundamentals
            if isinstance(data_payload, dict):
                df_data = data_payload.get('dataframe')
                fundamentals = data_payload.get('fundamentals')
            else:
                raise ValueError("data_payload must be a dict")
            
            logger.info(f"AnalysisAgent: reconstructing DataFrame from {len(df_data) if df_data else 'None'} records")
            if df_data is None:
                raise ValueError("Missing 'dataframe' in payload")
            
            # Reconstruct DataFrame from the list of records
            df = pd.DataFrame.from_dict(df_data)
            logger.info(f"DataFrame constructed: rows={len(df)}, cols={list(df.columns)}")
            
            # Normalize column names to lowercase (yfinance returns capitalized)
            df.columns = [col.lower() for col in df.columns]
            logger.info(f"Columns normalized to lowercase: {list(df.columns)}")
            
            # The records should have a 'date' column; set as index
            if 'date' in df.columns:
                df.set_index('date', inplace=True)
            df.index = pd.to_datetime(df.index)
            logger.info(f"DataFrame after set_index: rows={len(df)}, index range: {df.index.min()} to {df.index.max()}")
            
            snapshot = self._calculate_all(df, symbol, fundamentals=fundamentals)
            message = f"Indicators calculated for {symbol} at {snapshot.timestamp.isoformat()}"
            flow("AnalysisAgent", "DONE", f"{symbol} → {len(snapshot.indicators)} indicators")
            
            # Publish ANALYSIS_COMPLETE event with snapshot wrapped in dict (required by EventBus)
            # Use key 'indicators_snapshot' to match StrategyAgent expectations
            await self.event_bus.publish(Event(
                event_type=Events.ANALYSIS_COMPLETE,
                data={"indicators_snapshot": snapshot}
            ))
            
            # Return an AgentReport with the snapshot wrapped in a dict for compatibility with StrategyAgent
            return AgentReport(
                agent_id=self.agent_id,
                status="success",
                message=message,
                payload={"indicators_snapshot": snapshot}
            )
        except ValueError as e:
            logger.warning(f"AnalysisAgent failed for {symbol}: {e}")
            # Publish ANALYSIS_FAILED event
            await self.event_bus.publish(Event(
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
            await self.event_bus.publish(Event(
                event_type=Events.ANALYSIS_FAILED,
                data={"symbol": symbol, "reason": str(e)}
            ))
            return AgentReport(
                agent_id=self.agent_id,
                status="error",
                message=f"Unexpected error during analysis for {symbol}: {e}"
            )

    def _calculate_all(self, df: pd.DataFrame, symbol: str, fundamentals: Optional[Dict[str, Any]] = None) -> IndicatorsSnapshot:
        """
        Calculate all indicators for a symbol
        
        Args:
            df: OHLCV DataFrame with datetime index
            symbol: Symbol name
            fundamentals: Optional dict containing fundamental data (pe_ratio, revenue_growth_yoy, news_sentiment)
        
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
            indicators['sma_200'] = self.sma(df, 200)
            indicators['ema_12'] = self.ema(df, 12)
            indicators['ema_26'] = self.ema(df, 26)
            indicators['atr'] = self.atr(df)
            indicators['bb'] = self.bollinger_bands(df)
            indicators['stoch'] = self.stochastic(df)
            indicators['regime_score'] = self.regime_score(df)
            
            # Integrate fundamental indicators if provided (for backtest news simulation, etc.)
            if fundamentals:
                # News sentiment (proxy from backtest or real)
                if 'news_sentiment' in fundamentals:
                    ns = fundamentals['news_sentiment']
                    if ns is not None and not pd.isna(ns):
                        if ns > 0.3:
                            signal = SignalType.BUY
                        elif ns < -0.3:
                            signal = SignalType.SELL
                        else:
                            signal = SignalType.HOLD
                        indicators['news_sentiment'] = IndicatorResult(
                            name='news_sentiment',
                            value=float(ns),
                            signal=signal,
                            timestamp=latest_ts,
                            metadata={'source': 'proxy', 'fundamental': True}
                        )
                # P/E Ratio
                if 'pe_ratio' in fundamentals:
                    pe = fundamentals['pe_ratio']
                    if pe is not None and not pd.isna(pe):
                        if pe < 15:
                            signal = SignalType.BUY
                        elif pe > 30:
                            signal = SignalType.SELL
                        else:
                            signal = SignalType.HOLD
                        indicators['pe_ratio'] = IndicatorResult(
                            name='pe_ratio',
                            value=float(pe),
                            signal=signal,
                            timestamp=latest_ts,
                            metadata={'fundamental': True}
                        )
                # Revenue Growth YoY
                if 'revenue_growth_yoy' in fundamentals:
                    rg = fundamentals['revenue_growth_yoy']
                    if rg is not None and not pd.isna(rg):
                        if rg > 0.20:
                            signal = SignalType.BUY
                        elif rg < 0:
                            signal = SignalType.SELL
                        else:
                            signal = SignalType.HOLD
                        indicators['revenue_growth_yoy'] = IndicatorResult(
                            name='revenue_growth_yoy',
                            value=float(rg),
                            signal=signal,
                            timestamp=latest_ts,
                            metadata={'fundamental': True}
                        )
            
            # Get latest close price as current_price
            try:
                current_price = float(df['close'].iloc[-1])
            except Exception as e:
                logger.warning(f"Could not get current_price for {symbol}: {e}")
                current_price = None
            
            logger.debug(f"Calculated {len(indicators)} indicators for {symbol} at {latest_ts}")
            
            return IndicatorsSnapshot(
                symbol=symbol,
                timestamp=latest_ts,
                indicators=indicators,
                current_price=current_price
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

    def regime_score(self, df: pd.DataFrame) -> IndicatorResult:
        """
        Composite Regime Score (0-1)
        
        Combines multiple indicators to detect bull/bear market regimes:
        - SMA200 (30% weight): price above SMA200 = bullish
        - 52-week high proximity (40% weight): within 10% of 52w high = bullish
        - ADX trend strength (20% weight): ADX>25 + +DI>-DI = strong bullish trend
        - RSI midpoint (10% weight): RSI>50 = bullish momentum
        
        Returns:
            value: 0-100% bullish probability
            signal: BUY if >70%, SELL if <30%, HOLD otherwise
        """
        n = len(df)
        if n < 200:
            raise ValueError(f"Need 200+ bars for regime score, got {n}")
        close = float(df['close'].iloc[-1])
        lookback_sma = min(200, n)
        sma_200_series = df['close'].rolling(window=lookback_sma, min_periods=lookback_sma).mean()
        sma_200 = float(sma_200_series.iloc[-1])
        comp_sma200 = 1.0 if close > sma_200 else 0.0
        lookback_52w = min(252, n)
        high_period = df['high'].rolling(window=lookback_52w, min_periods=lookback_52w).max()
        high_52w = float(high_period.iloc[-1])
        pct_from_high = (close - high_52w) / high_52w if high_52w > 0 else -1.0
        comp_52w = 1.0 if pct_from_high >= -0.10 else 0.0
        comp_adx = 0.0
        if n >= 14:
            try:
                from ta.trend import ADXIndicator
                window_adx = min(14, n)
                adx_ind = ADXIndicator(high=df['high'], low=df['low'], close=df['close'], window=window_adx)
                adx_series = adx_ind.adx()
                plus_di_series = adx_ind.adx_pos()
                minus_di_series = adx_ind.adx_neg()
                if len(adx_series) > 0:
                    adx = float(adx_series.iloc[-1])
                    plus_di = float(plus_di_series.iloc[-1])
                    minus_di = float(minus_di_series.iloc[-1])
                    comp_adx = 1.0 if (adx > 25 and plus_di > minus_di) else 0.0
            except Exception:
                comp_adx = 0.0
        comp_rsi = 0.0
        if n >= 14:
            try:
                from ta.momentum import RSIIndicator
                window_rsi = min(14, n)
                rsi_ind = RSIIndicator(close=df['close'], window=window_rsi)
                rsi_series = rsi_ind.rsi()
                if len(rsi_series) > 0:
                    rsi = float(rsi_series.iloc[-1])
                    comp_rsi = 1.0 if rsi > 50 else 0.0
            except Exception:
                comp_rsi = 0.0
        weights = {'sma200': 0.30, '52w': 0.40, 'adx': 0.20, 'rsi': 0.10}
        available = {
            'sma200': 1.0 if n >= 200 else 0.0,
            '52w': 1.0,
            'adx': 1.0 if n >= 14 else 0.0,
            'rsi': 1.0 if n >= 14 else 0.0
        }
        total_weight = sum(weights[k] * available[k] for k in weights)
        if total_weight == 0:
            composite = 0.0
        else:
            composite = (
                comp_sma200 * weights['sma200'] * available['sma200'] +
                comp_52w * weights['52w'] * available['52w'] +
                comp_adx * weights['adx'] * available['adx'] +
                comp_rsi * weights['rsi'] * available['rsi']
            ) / total_weight
        composite = max(0.0, min(1.0, composite))
        regime_pct = composite * 100.0
        if composite > 0.7:
            signal = SignalType.BUY
        elif composite < 0.3:
            signal = SignalType.SELL
        else:
            signal = SignalType.HOLD
        return IndicatorResult(
            name='regime_score',
            value=float(regime_pct),
            signal=signal,
            timestamp=df.index[-1],
            metadata={
                'components': {
                    'sma200': comp_sma200,
                    '52w_high': comp_52w,
                    'adx': comp_adx,
                    'rsi': comp_rsi
                },
                'interpretation': '0-100% bullish probability'
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
