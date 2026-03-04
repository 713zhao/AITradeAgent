# Phase 2 Action Plan: Indicators & Strategy Engine
**Weeks 4-5 (Days 1-10)**
**Status**: Ready to Start
**Last Updated**: 4 Mar 2026

---

## Phase 2 Overview

**Objective**: Build technical indicator calculator, rule-based strategy engine, and decision engine to transform raw OHLCV data into actionable trading decisions.

**Inputs**: DATA_READY events from Phase 1 (DataManager)
**Outputs**: DECISION_MADE events containing Decision JSON (symbol, signals, confidence, SL/TP)

**Key Constraints**:
- All indicators computed locally (no external ML/LLM)
- Deterministic output (reproducible results, no randomness)
- Sub-100ms calculation on 252-candle dataset
- All indicator parameters configurable via finance.yaml

**Architecture**:
```
DataManager (Phase 1)
    ↓
    [listens to DATA_READY]
    ↓
IndicatorCalculator (NEW)
    ├─ RSI, MACD, SMA, EMA, ATR, Bollinger Bands, Stochastic
    ↓
RuleStrategy (NEW)
    ├─ Entry rules (price > SMA, RSI < 30, etc.)
    ├─ Exit rules (profit target, stop loss, time-based)
    ↓
DecisionEngine (NEW)
    ├─ Confidence scoring
    ├─ Decision JSON generation
    ↓
EventBus → DECISION_MADE event
```

---

## Task Breakdown (10 Days)

### DAY 1-2: Indicator Calculator Core

#### Task 2.1: Create `finance_service/indicators/__init__.py`
- Purpose: Module exports and indicator interface
- File: `finance_service/indicators/__init__.py`
- Deliverable:
  ```python
  """Indicator calculations module"""
  from .calculator import IndicatorCalculator
  from .models import IndicatorResult, SignalType
  
  __all__ = ['IndicatorCalculator', 'IndicatorResult', 'SignalType']
  ```
- Checklist:
  - [x] File created
  - [ ] Imports working

#### Task 2.2: Create `finance_service/indicators/models.py`
- Purpose: Data classes for indicator results and signals
- File: `finance_service/indicators/models.py`
- Deliverable (~80 lines):
  ```python
  from enum import Enum
  from dataclasses import dataclass, asdict
  from typing import Dict, Any, Optional
  import pandas as pd
  
  class SignalType(Enum):
      BUY = "BUY"
      SELL = "SELL"
      HOLD = "HOLD"
      STRONG_BUY = "STRONG_BUY"
      STRONG_SELL = "STRONG_SELL"
  
  @dataclass
  class IndicatorResult:
      """Result of indicator calculation"""
      name: str  # 'rsi', 'macd', 'sma_20', etc.
      value: float
      signal: SignalType
      timestamp: pd.Timestamp
      metadata: Dict[str, Any] = None  # Extra data (histogram, signal_line, etc.)
      
      def to_dict(self):
          return asdict(self)
  
  @dataclass
  class IndicatorsSnapshot:
      """All indicators calculated for a symbol at a timestamp"""
      symbol: str
      timestamp: pd.Timestamp
      indicators: Dict[str, IndicatorResult]  # {'rsi': IndicatorResult(...), ...}
      
      def get_all_signals(self) -> Dict[str, SignalType]:
          return {k: v.signal for k, v in self.indicators.items()}
  ```
- Checklist:
  - [ ] File created
  - [ ] SignalType enum defined
  - [ ] IndicatorResult dataclass defined
  - [ ] IndicatorsSnapshot dataclass defined

#### Task 2.3: Create `finance_service/indicators/calculator.py` - Part 1 (Infrastructure)
- Purpose: Core IndicatorCalculator class with 7 indicator methods
- File: `finance_service/indicators/calculator.py`
- Lines: ~600 (650 total with Part 2)
- Part 1 Content (~300 lines):
  ```python
  """Technical indicator calculations"""
  import pandas as pd
  import numpy as np
  from typing import Dict, Tuple
  from .models import IndicatorResult, IndicatorsSnapshot, SignalType
  import logging
  
  logger = logging.getLogger(__name__)
  
  class IndicatorCalculator:
      """Computes technical indicators from OHLCV data"""
      
      def __init__(self, periods_config: Dict = None):
          """
          Args:
              periods_config: {'rsi_period': 14, 'sma_periods': [20, 50], ...}
          """
          self.periods = periods_config or self._default_periods()
          
      @staticmethod
      def _default_periods():
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
          """Calculate all indicators for a symbol"""
          if len(df) < 50:
              raise ValueError(f"Insufficient data: {len(df)} rows, need 50+")
          
          indicators = {}
          latest_idx = len(df) - 1
          latest_ts = df.index[-1]
          
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
          
          return IndicatorsSnapshot(
              symbol=symbol,
              timestamp=latest_ts,
              indicators=indicators
          )
      
      def rsi(self, df: pd.DataFrame, period: int = 14) -> IndicatorResult:
          """
          Relative Strength Index
          RSI = 100 - (100 / (1 + RS))
          RS = avg_gain / avg_loss
          """
          delta = df['close'].diff()
          gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
          loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
          
          rs = gain / loss
          rsi_values = 100 - (100 / (1 + rs))
          rsi = rsi_values.iloc[-1]
          
          # Signal: RSI < 30 = BUY, RSI > 70 = SELL
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
              metadata={'period': period}
          )
      
      def macd(self, df: pd.DataFrame) -> IndicatorResult:
          """
          MACD (Moving Average Convergence Divergence)
          MACD = EMA12 - EMA26
          Signal = EMA9(MACD)
          Histogram = MACD - Signal
          """
          ema12 = df['close'].ewm(span=12).mean()
          ema26 = df['close'].ewm(span=26).mean()
          
          macd_line = ema12 - ema26
          signal_line = macd_line.ewm(span=9).mean()
          histogram = macd_line - signal_line
          
          current_macd = float(macd_line.iloc[-1])
          current_signal = float(signal_line.iloc[-1])
          current_hist = float(histogram.iloc[-1])
          prev_hist = float(histogram.iloc[-2]) if len(histogram) > 1 else 0
          
          # Signal: Histogram crossing 0 (bullish/bearish)
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
                  'signal_line': current_signal,
                  'histogram': current_hist
              }
          )
      
      def sma(self, df: pd.DataFrame, period: int = 20) -> IndicatorResult:
          """Simple Moving Average"""
          sma_values = df['close'].rolling(window=period).mean()
          sma = float(sma_values.iloc[-1])
          current_price = float(df['close'].iloc[-1])
          
          # Signal: Price above/below SMA
          if current_price > sma * 1.01:  # 1% above
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
              metadata={'period': period, 'price': current_price}
          )
      
      def ema(self, df: pd.DataFrame, period: int = 12) -> IndicatorResult:
          """Exponential Moving Average"""
          ema_values = df['close'].ewm(span=period).mean()
          ema = float(ema_values.iloc[-1])
          current_price = float(df['close'].iloc[-1])
          
          # Signal: Same as SMA
          if current_price > ema * 1.01:
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
              metadata={'period': period, 'price': current_price}
          )
  ```
- Checklist:
  - [ ] File created
  - [ ] IndicatorCalculator class defined
  - [ ] __init__ with periods configuration
  - [ ] calculate_all() method working
  - [ ] RSI calculator unit tested
  - [ ] MACD calculator unit tested
  - [ ] SMA calculator unit tested
  - [ ] EMA calculator unit tested

---

### DAY 3: Indicator Calculator Part 2 (Remaining Indicators)

#### Task 2.4: Create `finance_service/indicators/calculator.py` - Part 2 (ATR, Bollinger, Stochastic)
- Purpose: Complete indicator set
- Append to existing file (~300 lines additional)
- Content:
  ```python
      def atr(self, df: pd.DataFrame, period: int = 14) -> IndicatorResult:
          """
          Average True Range
          TR = max(H-L, abs(H-PC), abs(L-PC))
          ATR = EMA(TR, period)
          """
          high = df['high']
          low = df['low']
          close = df['close']
          
          tr1 = high - low
          tr2 = abs(high - close.shift())
          tr3 = abs(low - close.shift())
          
          tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
          atr_values = tr.ewm(span=period).mean()
          atr = float(atr_values.iloc[-1])
          
          # Signal: Based on volatility (no buy/sell, used for SL/TP)
          return IndicatorResult(
              name='atr',
              value=atr,
              signal=SignalType.HOLD,
              timestamp=df.index[-1],
              metadata={'period': period}
          )
      
      def bollinger_bands(self, df: pd.DataFrame, period: int = 20, std: float = 2.0) -> IndicatorResult:
          """
          Bollinger Bands
          Middle = SMA(close, period)
          Upper = Middle + (std * StdDev)
          Lower = Middle - (std * StdDev)
          """
          sma = df['close'].rolling(window=period).mean()
          std_dev = df['close'].rolling(window=period).std()
          
          upper_band = sma + (std * std_dev)
          lower_band = sma - (std * std_dev)
          
          current_price = float(df['close'].iloc[-1])
          current_upper = float(upper_band.iloc[-1])
          current_lower = float(lower_band.iloc[-1])
          current_sma = float(sma.iloc[-1])
          
          # Signal: Price touching bands
          if current_price > current_upper * 0.99:
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
                  'lower': current_lower,
                  'price': current_price
              }
          )
      
      def stochastic(self, df: pd.DataFrame, k_period: int = 14, d_period: int = 3) -> IndicatorResult:
          """
          Stochastic Oscillator
          %K = 100 * (Close - Lowest Low) / (Highest High - Lowest Low)
          %D = SMA(%K, d_period)
          """
          high_high = df['high'].rolling(window=k_period).max()
          low_low = df['low'].rolling(window=k_period).min()
          
          k_percent = 100 * ((df['close'] - low_low) / (high_high - low_low))
          d_percent = k_percent.rolling(window=d_period).mean()
          
          current_k = float(k_percent.iloc[-1])
          current_d = float(d_percent.iloc[-1])
          prev_k = float(k_percent.iloc[-2]) if len(k_percent) > 1 else current_k
          prev_d = float(d_percent.iloc[-2]) if len(d_percent) > 1 else current_d
          
          # Signal: K crossing D or oversold/overbought
          if current_k < 20:
              signal = SignalType.BUY
          elif current_k > 80:
              signal = SignalType.SELL
          elif current_k > prev_k and current_k > current_d:
              signal = SignalType.BUY
          elif current_k < prev_k and current_k < current_d:
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
      
      def _validate_ohlcv(self, df: pd.DataFrame) -> None:
          """Validate OHLCV data"""
          required_cols = {'open', 'high', 'low', 'close', 'volume'}
          if not required_cols.issubset(df.columns):
              raise ValueError(f"Missing columns. Need {required_cols}, got {set(df.columns)}")
          
          if len(df) < 50:
              raise ValueError(f"Need 50+ candles, got {len(df)}")
          
          if df.isnull().any().any():
              raise ValueError("Data contains NaN values")
  ```
- Checklist:
  - [ ] ATR calculator added
  - [ ] Bollinger Bands calculator added
  - [ ] Stochastic calculator added
  - [ ] Data validation method added
  - [ ] All 7 indicators unit tested

---

### DAY 4: Rule-Based Strategy Engine

#### Task 2.5: Create `finance_service/strategies/__init__.py`
- File: `finance_service/strategies/__init__.py`
- Content:
  ```python
  """Strategies module"""
  from .rule_strategy import RuleStrategy
  from .decision_engine import DecisionEngine
  
  __all__ = ['RuleStrategy', 'DecisionEngine']
  ```
- Checklist:
  - [ ] File created

#### Task 2.6: Create `finance_service/strategies/rule_strategy.py`
- Purpose: Rule-based entry/exit logic
- File: `finance_service/strategies/rule_strategy.py`
- Lines: ~350
- Content Structure:
  ```python
  """Rule-based trading strategy engine"""
  from dataclasses import dataclass
  from typing import Dict, List, Tuple, Optional
  from enum import Enum
  import pandas as pd
  import yaml
  
  class RuleType(Enum):
      ENTRY = "entry"
      EXIT = "exit"
  
  @dataclass
  class Rule:
      """Single trading rule"""
      name: str  # 'rsi_oversold', 'price_above_sma', etc.
      type: RuleType  # ENTRY or EXIT
      indicator: str  # 'rsi', 'macd', 'price', etc.
      condition: str  # 'less_than', 'greater_than', 'crosses_above', etc.
      value: float  # threshold value
      enabled: bool = True
      
  class RuleStrategy:
      """Evaluates entry/exit rules against indicators"""
      
      def __init__(self, rules_config: List[Dict]):
          """Load rules from config"""
          self.rules = self._parse_rules(rules_config)
          self.entry_rules = [r for r in self.rules if r.type == RuleType.ENTRY]
          self.exit_rules = [r for r in self.rules if r.type == RuleType.EXIT]
      
      def _parse_rules(self, rules_config: List[Dict]) -> List[Rule]:
          """Parse rules from YAML config"""
          rules = []
          for rule_cfg in rules_config:
              rule = Rule(
                  name=rule_cfg.get('name'),
                  type=RuleType(rule_cfg.get('type', 'entry')),
                  indicator=rule_cfg.get('indicator'),
                  condition=rule_cfg.get('condition'),
                  value=rule_cfg.get('value'),
                  enabled=rule_cfg.get('enabled', True)
              )
              rules.append(rule)
          return rules
      
      def evaluate_entry(self, indicators_snapshot) -> Tuple[bool, float, List[str]]:
          """
          Evaluate entry rules
          Returns: (should_buy, confidence_0_to_1, triggered_rules)
          """
          triggered = []
          scores = []
          
          for rule in self.entry_rules:
              if not rule.enabled:
                  continue
              
              # Get indicator value
              ind = indicators_snapshot.indicators.get(rule.indicator)
              if not ind:
                  continue
              
              # Evaluate condition
              if self._check_condition(ind.value, rule.condition, rule.value):
                  triggered.append(rule.name)
                  scores.append(1.0)
          
          if not triggered:
              return False, 0.0, []
          
          confidence = sum(scores) / len(self.entry_rules)  # % of rules triggered
          return True, confidence, triggered
      
      def evaluate_exit(self, indicators_snapshot) -> Tuple[bool, List[str]]:
          """
          Evaluate exit rules
          Returns: (should_sell, triggered_rules)
          """
          triggered = []
          
          for rule in self.exit_rules:
              if not rule.enabled:
                  continue
              
              ind = indicators_snapshot.indicators.get(rule.indicator)
              if not ind:
                  continue
              
              if self._check_condition(ind.value, rule.condition, rule.value):
                  triggered.append(rule.name)
          
          return len(triggered) > 0, triggered
      
      @staticmethod
      def _check_condition(value: float, condition: str, threshold: float) -> bool:
          """Check if condition is met"""
          if condition == 'less_than':
              return value < threshold
          elif condition == 'greater_than':
              return value > threshold
          elif condition == 'equals':
              return abs(value - threshold) < 0.001
          # Add more conditions as needed
          return False
  ```
- Checklist:
  - [ ] File created
  - [ ] Rule dataclass defined
  - [ ] RuleStrategy class with entry/exit evaluation
  - [ ] Config parsing from YAML
  - [ ] Condition evaluation logic
  - [ ] Confidence calculation

---

### DAY 5: Decision Engine

#### Task 2.7: Create `finance_service/strategies/decision_engine.py`
- Purpose: Convert indicators + rules → Decision JSON
- File: `finance_service/strategies/decision_engine.py`
- Lines: ~280
- Content:
  ```python
  """Decision generation from indicators and rules"""
  from dataclasses import dataclass, asdict
  from typing import Dict, Optional, List
  import pd as
  from finance_service.core.models import Decision
  from finance_service.indicators.models import SignalType
  import logging
  
  logger = logging.getLogger(__name__)
  
  @dataclass
  class DecisionContext:
      """Context for decision making"""
      symbol: str
      current_price: float
      atr: float  # For stop loss / take profit sizing
      entry_triggered: bool
      entry_confidence: float
      entry_rules: List[str]
      exit_triggered: bool
      exit_rules: List[str]
      all_signals: Dict[str, SignalType]
  
  class DecisionEngine:
      """
      Converts indicators + rules into trading decisions
      Output: Decision JSON with symbol, decision, confidence, SL/TP
      """
      
      def __init__(self, atr_multiplier_sl: float = 2.0, atr_multiplier_tp: float = 3.0):
          """
          Args:
              atr_multiplier_sl: Stop loss distance = current_price - (atr * 2)
              atr_multiplier_tp: Take profit distance = current_price + (atr * 3)
          """
          self.atr_multiplier_sl = atr_multiplier_sl
          self.atr_multiplier_tp = atr_multiplier_tp
      
      def make_decision(self, context: DecisionContext) -> Decision:
          """
          Generate trading decision
          Args:
              context: DecisionContext with all indicators and rules evaluated
          
          Returns:
              Decision: {'symbol', 'decision', 'confidence', 'signals', 'stop_loss', 'take_profit'}
          """
          
          # Determine decision
          if context.exit_triggered:
              decision = "SELL"
              confidence = 0.7  # Exit decisions are less precise
              signals = context.exit_rules
          elif context.entry_triggered:
              decision = "BUY"
              confidence = context.entry_confidence
              signals = context.entry_rules
          else:
              decision = "HOLD"
              confidence = 0.0
              signals = []
          
          # Calculate stop loss and take profit
          stop_loss, take_profit = self._calculate_sl_tp(
              context.current_price,
              context.atr,
              decision
          )
          
          # Build Decision object
          dec = Decision(
              symbol=context.symbol,
              decision=decision,
              confidence=min(confidence, 1.0),  # Cap at 1.0
              signals=signals,
              stop_loss=stop_loss,
              take_profit=take_profit,
              timestamp=pd.Timestamp.now()
          )
          
          logger.info(f"Decision: {context.symbol} → {decision} (conf: {confidence:.2%})")
          return dec
      
      def _calculate_sl_tp(self, price: float, atr: float, decision: str) -> Tuple[float, float]:
          """Calculate stop loss and take profit levels"""
          if decision == "BUY":
              sl = price - (atr * self.atr_multiplier_sl)
              tp = price + (atr * self.atr_multiplier_tp)
          elif decision == "SELL":
              sl = price + (atr * self.atr_multiplier_sl)  # Higher
              tp = price - (atr * self.atr_multiplier_tp)  # Lower
          else:
              sl = None
              tp = None
          
          return round(sl, 2) if sl else None, round(tp, 2) if tp else None
  ```
- Checklist:
  - [ ] File created
  - [ ] DecisionContext dataclass defined
  - [ ] DecisionEngine class
  - [ ] make_decision() method
  - [ ] SL/TP calculation logic
  - [ ] Confidence calculation

---

### DAY 6: Integration with Phase 1 & Event Emission

#### Task 2.8: Update `finance_service/app.py` - Add Phase 2 Integration
- Purpose: Subscribe to DATA_READY, trigger indicators/strategy, emit DECISION_MADE
- File: `finance_service/app.py` (append ~150 lines)
- Changes:
  ```python
  from finance_service.indicators.calculator import IndicatorCalculator
  from finance_service.strategies.rule_strategy import RuleStrategy
  from finance_service.strategies.decision_engine import DecisionEngine, DecisionContext
  
  # -- Add to Flask app initialization --
  
  # Initialize Phase 2 components
  indicator_calc = IndicatorCalculator()
  strategy = RuleStrategy(config.get_raw('finance', 'strategies/entry_rules'))
  decision_engine = DecisionEngine()
  
  # Subscribe to DATA_READY events
  @event_bus.on("DATA_READY")
  def on_data_ready(event):
      """
      Triggered when DataManager submits DATA_READY
      Flow: Get OHLCV → Calculate indicators → Evaluate rules → Make decision → Emit DECISION_MADE
      """
      symbol = event['data']['symbol']
      interval = event['data']['interval']
      
      try:
          # Get OHLCV data
          df = data_manager.get_data(symbol, interval)
          
          # Calculate all indicators
          ind_snapshot = indicator_calc.calculate_all(df, symbol)
          
          # Evaluate strategy rules
          entry_triggered, entry_conf, entry_rules = strategy.evaluate_entry(ind_snapshot)
          exit_triggered, exit_rules = strategy.evaluate_exit(ind_snapshot)
          
          # Build decision context
          atr_value = ind_snapshot.indicators['atr'].value
          current_price = float(df['close'].iloc[-1])
          
          context = DecisionContext(
              symbol=symbol,
              current_price=current_price,
              atr=atr_value,
              entry_triggered=entry_triggered,
              entry_confidence=entry_conf,
              entry_rules=entry_rules,
              exit_triggered=exit_triggered,
              exit_rules=exit_rules,
              all_signals=ind_snapshot.get_all_signals()
          )
          
          # Make decision
          decision = decision_engine.make_decision(context)
          
          # Emit DECISION_MADE event
          event_bus.publish({
              'type': 'DECISION_MADE',
              'symbol': symbol,
              'decision': decision.to_dict(),
              'timestamp': pd.Timestamp.now().isoformat()
          })
          
      except Exception as e:
          logger.error(f"Error processing {symbol}: {e}")
          event_bus.publish({
              'type': 'ANALYSIS_FAILED',
              'symbol': symbol,
              'error': str(e)
          })
  ```
- Checklist:
  - [ ] Imports added
  - [ ] Phase 2 components initialized
  - [ ] Event listener on DATA_READY
  - [ ] Data retrieval from DataManager
  - [ ] Indicator calculation
  - [ ] Rule evaluation
  - [ ] Decision engine
  - [ ] DECISION_MADE event emission
  - [ ] Error handling with ANALYSIS_FAILED event

#### Task 2.9: Update `config/finance.yaml` - Add Strategy Rules
- Purpose: Define entry/exit rules
- Changes:
  ```yaml
  strategies:
    entry_rules:
      - name: "rsi_oversold"
        type: "entry"
        indicator: "rsi"
        condition: "less_than"
        value: 30
        enabled: true
      
      - name: "price_above_sma20"
        type: "entry"
        indicator: "sma_20"
        condition: "greater_than"
        value: 0.99  # 99% of SMA value (1% tolerance)
        enabled: true
      
      - name: "macd_bullish_cross"
        type: "entry"
        indicator: "macd"
        condition: "greater_than"
        value: 0  # MACD > 0
        enabled: false  # Optional
    
    exit_rules:
      - name: "rsi_overbought"
        type: "exit"
        indicator: "rsi"
        condition: "greater_than"
        value: 70
        enabled: true
      
      - name: "price_below_sma50"
        type: "exit"
        indicator: "sma_50"
        condition: "less_than"
        value: 1.01
        enabled: true
  ```
- Checklist:
  - [ ] entry_rules section added
  - [ ] exit_rules section added
  - [ ] Rule names descriptive
  - [ ] Conditions valid
  - [ ] At least 3 entry + 2 exit rules

---

### DAY 7-8: Comprehensive Unit Tests

#### Task 2.10: Create `tests/test_phase2_indicators.py`
- Purpose: Unit test all indicators
- File: `tests/test_phase2_indicators.py`
- Lines: ~400
- Test Classes:
  - `TestRSI`: 4 tests (normal, oversold, overbought, edge)
  - `TestMACD`: 4 tests (bullish cross, bearish cross, no cross, signal line)
  - `TestSMA`: 3 tests (above SMA, below SMA, at SMA)
  - `TestEMA`: 3 tests (above EMA, below EMA, crossover)
  - `TestATR`: 2 tests (normal volatility, spike)
  - `TestBollingerBands`: 4 tests (touch upper, touch lower, within bands, squeeze)
  - `TestStochastic`: 3 tests (oversold, overbought, K crossover D)
- Expected: 23/23 passing
- Checklist:
  - [ ] File created
  - [ ] 7 indicator test classes
  - [ ] 23 test methods
  - [ ] All >80% accuracy vs expected values
  - [ ] Edge cases covered

#### Task 2.11: Create `tests/test_phase2_strategy.py`
- Purpose: Unit test strategy rules
- File: `tests/test_phase2_strategy.py`
- Lines: ~250
- Test Classes:
  - `TestRuleEvaluation`: 5 tests (entry rules triggered, no trigger, partial trigger, exit rules)
  - `TestRuleStrategy`: 4 tests (load rules from config, missing rules, disabled rules, confidence calc)
  - `TestDecisionEngine`: 5 tests (buy decision, sell decision, hold, SL/TP calculation, edge prices)
- Expected: 14/14 passing
- Checklist:
  - [ ] File created
  - [ ] RuleStrategy tests
  - [ ] DecisionEngine tests
  - [ ] Decision JSON validation
  - [ ] SL/TP accuracy

#### Task 2.12: Create `tests/test_phase2_integration.py`
- Purpose: End-to-end flow test
- File: `tests/test_phase2_integration.py`
- Lines: ~200
- Test Scenarios:
  - `test_data_ready_to_decision_made`: DATA_READY → indicators → decision → DECISION_MADE event
  - `test_multiple_symbols_concurrent`: Parallel processing of 5 symbols
  - `test_event_order`: Verify event sequence
  - `test_timing`: Sub-100ms calculation on 252 candles
- Expected: 4/4 passing
- Checklist:
  - [ ] Integration test file created
  - [ ] Event flow validated
  - [ ] Concurrent processing tested
  - [ ] Timing performance validated

---

### DAY 9: Documentation & Completion Report

#### Task 2.13: Create `PHASE2_COMPLETION_REPORT.md`
- Purpose: Document Phase 2 deliverables, metrics, lessons learned
- File: `PHASE2_COMPLETION_REPORT.md`
- Sections:
  - Deliverables checklist (all files created)
  - Metrics (indicator accuracy, decision latency, test coverage)
  - Event flow diagram
  - Configuration guide (how to modify rules in finance.yaml)
  - Lessons learned
- Checklist:
  - [ ] Report created
  - [ ] All metrics documented
  - [ ] Configuration guide included

---

### DAY 10: Final Validation & Phase 2 Handoff

#### Task 2.14: Run Full Phase 2 Validation
- Purpose: Verify all components working end-to-end
- Commands:
  ```bash
  # 1. Unit tests - indicators
  pytest tests/test_phase2_indicators.py -v
  
  # 2. Unit tests - strategy
  pytest tests/test_phase2_strategy.py -v
  
  # 3. Integration tests
  pytest tests/test_phase2_integration.py -v
  
  # 4. Combined Phase 1 + Phase 2 test
  pytest tests/test_phase1_data_layer.py tests/test_phase2_indicators.py tests/test_phase2_strategy.py -v
  
  # 5. Performance check (should be <100ms per symbol for 252 candles)
  python -m pytest tests/test_phase2_integration.py::test_timing -v
  ```
- Success Criteria:
  - [x] All indicator tests passing (23/23)
  - [x] All strategy tests passing (14/14)
  - [x] All integration tests passing (4/4)
  - [x] Performance <100ms per symbol
  - [x] Deterministic output (no randomness)
  - [x] Decision JSON valid for all cases
- Checklist:
  - [ ] All tests passing
  - [ ] Performance validated
  - [ ] Code review completed
  - [ ] Documentation updated

#### Task 2.15: Update Master Plan
- File: `PLAN_IMPLEMENTATION_V4.md`
- Changes:
  - Mark Phase 2 as COMPLETE with ✅
  - Document completion date (Fri, Week 5)
  - Update status to "Phase 3 - In Progress"
  - Link to `PHASE2_COMPLETION_REPORT.md`
  - Update Phase 3 preview section
- Checklist:
  - [ ] PLAN_IMPLEMENTATION_V4.md updated
  - [ ] Phase 2 marked complete
  - [ ] Phase 3 status set to IN PROGRESS
  - [ ] PHASE2_COMPLETION_REPORT.md linked

---

## Daily Progress Tracking

| Day | Task | Status | Notes |
|-----|------|--------|-------|
| 1-2 | 2.1-2.3: Indicator core | ⬜ | IndicatorCalculator RSI, MACD, SMA, EMA |
| 3 | 2.4: Indicator complete | ⬜ | ATR, Bollinger Bands, Stochastic |
| 4 | 2.5-2.6: Strategy rules | ⬜ | RuleStrategy, rule evaluation |
| 5 | 2.7-2.9: Decision engine | ⬜ | DecisionEngine, app integration, config |
| 6 | (Continued from 5) | ⬜ | Finance.yaml rules configuration |
| 7-8 | 2.10-2.12: Unit tests | ⬜ | 23 indicator + 14 strategy + 4 integration tests |
| 9 | 2.13: Docs + report | ⬜ | PHASE2_COMPLETION_REPORT.md |
| 10 | 2.14-2.15: Validation | ⬜ | All tests passing, plan updated |

### How to Use This Tracker
- Mark `⬜` as `🟨` when starting a task
- Mark `🟨` as `✅` when task complete and tested
- Add notes if blocked or changes needed

---

## Testing Commands (Ready to Run)

```bash
# Phase 2 Indicators Test
pytest tests/test_phase2_indicators.py -v --tb=short

# Phase 2 Strategy Test
pytest tests/test_phase2_strategy.py -v --tb=short

# Phase 2 Integration Test
pytest tests/test_phase2_integration.py -v --tb=short

# All Phase 2 Tests
pytest tests/test_phase2_*.py -v

# Combined Phases 1 + 2 Validation
pytest tests/test_phase1_data_layer.py tests/test_phase2_indicators.py tests/test_phase2_strategy.py tests/test_phase2_integration.py -v

# Performance validation (< 100ms per symbol)
time pytest tests/test_phase2_integration.py::test_timing -v
```

---

## Dependencies on Phase 1

- ✅ `finance_service/data/data_manager.py` - Get OHLCV data
- ✅ `finance_service/core/event_bus.py` - Subscribe to DATA_READY, publish DECISION_MADE
- ✅ `finance_service/core/yaml_config.py` - Load strategy rules from finance.yaml
- ✅ `config/finance.yaml` - Strategy rules configuration

**Status**: All Phase 1 dependencies available ✅

---

## Success Criteria Summary

- [ ] 7 indicators implemented with >80% accuracy
- [ ] Rule evaluation working (entry/exit)
- [ ] Decision engine producing valid Decision JSON
- [ ] Event integration: DATA_READY → DECISION_MADE
- [ ] All 41 tests passing (23 + 14 + 4)
- [ ] Sub-100ms latency on 252-candle datasets
- [ ] Deterministic output (reproducible results)
- [ ] Configuration-driven (all rules in finance.yaml)
- [ ] Phase 2 completion report generated
- [ ] PLAN_IMPLEMENTATION_V4.md marked complete

---

## Notes for Implementation

1. **Numpy/Pandas Performance**: Use vectorized operations, avoid loops
2. **Signal Definitions**: Each indicator should return explicit SignalType (BUY/SELL/HOLD)
3. **Confidence Scoring**: Entry confidence = (rules triggered) / (total entry rules)
4. **ATR for Risk**: ATR size used for SL/TP sizing, not direct signal
5. **Deterministic**: No random thresholds, all config-driven
6. **Dataframe Index**: Ensure datetime index on all OHLCV dataframes
7. **Error Handling**: Log all errors, emit ANALYSIS_FAILED on exception
8. **Testing**: Use pytest fixtures for sample OHLCV data (50-252 rows)

---

**Ready to start?** Run Task 2.1 and mark ✅ when complete!
