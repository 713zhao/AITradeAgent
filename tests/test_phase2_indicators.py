"""Phase 2 Tests: Indicators, Strategy, and Decision Engine"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from finance_service.indicators.calculator import IndicatorCalculator
from finance_service.indicators.models import IndicatorResult, IndicatorsSnapshot, SignalType
from finance_service.strategies.rule_strategy import RuleStrategy, RuleType, Rule
from finance_service.strategies.decision_engine import DecisionEngine, DecisionContext


# =====================
# FIXTURES
# =====================

@pytest.fixture
def sample_ohlcv_data():
    """Generate sample OHLCV data for testing"""
    dates = pd.date_range(end=datetime.now(), periods=252, freq='D')
    np.random.seed(42)
    
    close = 100 + np.cumsum(np.random.randn(252) * 2)
    high = close + np.abs(np.random.randn(252))
    low = close - np.abs(np.random.randn(252))
    volume = np.random.randint(1000000, 10000000, 252)
    
    df = pd.DataFrame({
        'open': close + np.random.randn(252),
        'high': high,
        'low': low,
        'close': close,
        'volume': volume
    }, index=dates)
    
    return df


@pytest.fixture
def indicator_calculator():
    """Create IndicatorCalculator instance"""
    return IndicatorCalculator()


@pytest.fixture
def sample_strategy_rules():
    """Sample strategy rules for testing"""
    return [
        {
            'name': 'rsi_oversold',
            'type': 'entry',
            'indicator': 'rsi',
            'condition': 'less_than',
            'value': 30,
            'enabled': True
        },
        {
            'name': 'price_above_sma20',
            'type': 'entry',
            'indicator': 'sma_20',
            'condition': 'greater_than',
            'value': 95,
            'enabled': True
        },
        {
            'name': 'rsi_overbought',
            'type': 'exit',
            'indicator': 'rsi',
            'condition': 'greater_than',
            'value': 70,
            'enabled': True
        }
    ]


@pytest.fixture
def rule_strategy(sample_strategy_rules):
    """Create RuleStrategy instance"""
    return RuleStrategy(sample_strategy_rules)


@pytest.fixture
def decision_engine():
    """Create DecisionEngine instance"""
    return DecisionEngine(atr_multiplier_sl=2.0, atr_multiplier_tp=3.0)


# =====================
# INDICATOR CALCULATOR TESTS
# =====================

class TestIndicatorCalculator:
    """Test IndicatorCalculator"""
    
    def test_initialization(self, indicator_calculator):
        """Test calculator initializes with default periods"""
        assert indicator_calculator is not None
        assert indicator_calculator.periods is not None
        assert indicator_calculator.periods['rsi'] == 14
    
    def test_calculate_all(self, indicator_calculator, sample_ohlcv_data):
        """Test calculate_all returns IndicatorsSnapshot"""
        snapshot = indicator_calculator.calculate_all(sample_ohlcv_data, 'AAPL')
        
        assert isinstance(snapshot, IndicatorsSnapshot)
        assert snapshot.symbol == 'AAPL'
        assert len(snapshot.indicators) == 9  # 7 indicators
        assert 'rsi' in snapshot.indicators
        assert 'macd' in snapshot.indicators
        assert 'sma_20' in snapshot.indicators
    
    def test_insufficient_data(self, indicator_calculator):
        """Test error on insufficient data"""
        df = pd.DataFrame({
            'open': [100],
            'high': [101],
            'low': [99],
            'close': [100.5],
            'volume': [1000000]
        })
        
        with pytest.raises(ValueError):
            indicator_calculator.calculate_all(df, 'AAPL')
    
    def test_rsi_calculation(self, indicator_calculator, sample_ohlcv_data):
        """Test RSI indicator"""
        result = indicator_calculator.rsi(sample_ohlcv_data)
        
        assert isinstance(result, IndicatorResult)
        assert result.name == 'rsi'
        assert 0 <= result.value <= 100
        assert isinstance(result.signal, SignalType)
    
    def test_rsi_oversold_signal(self, indicator_calculator):
        """Test RSI generates BUY signal when oversold"""
        # Create data with downtrend (low RSI)
        dates = pd.date_range(end=datetime.now(), periods=50, freq='D')
        prices = [100 - i for i in range(50)]  # Downtrend
        
        df = pd.DataFrame({
            'open': prices,
            'high': prices,
            'low': [p - 1 for p in prices],
            'close': prices,
            'volume': [1000000] * 50
        }, index=dates)
        
        result = indicator_calculator.rsi(df)
        assert result.value < 50  # Downtrend = low RSI
    
    def test_macd_calculation(self, indicator_calculator, sample_ohlcv_data):
        """Test MACD indicator"""
        result = indicator_calculator.macd(sample_ohlcv_data)
        
        assert isinstance(result, IndicatorResult)
        assert result.name == 'macd'
        assert 'macd_line' in result.metadata
        assert 'signal_line' in result.metadata
        assert 'histogram' in result.metadata
    
    def test_sma_calculation(self, indicator_calculator, sample_ohlcv_data):
        """Test SMA indicator"""
        result = indicator_calculator.sma(sample_ohlcv_data, period=20)
        
        assert isinstance(result, IndicatorResult)
        assert result.name == 'sma_20'
        assert result.value > 0
        assert result.metadata['period'] == 20
    
    def test_ema_calculation(self, indicator_calculator, sample_ohlcv_data):
        """Test EMA indicator"""
        result = indicator_calculator.ema(sample_ohlcv_data, period=12)
        
        assert isinstance(result, IndicatorResult)
        assert result.name == 'ema_12'
        assert result.value > 0
    
    def test_atr_calculation(self, indicator_calculator, sample_ohlcv_data):
        """Test ATR indicator"""
        result = indicator_calculator.atr(sample_ohlcv_data)
        
        assert isinstance(result, IndicatorResult)
        assert result.name == 'atr'
        assert result.value > 0
        assert result.signal == SignalType.HOLD  # ATR not directional
    
    def test_bollinger_bands_calculation(self, indicator_calculator, sample_ohlcv_data):
        """Test Bollinger Bands indicator"""
        result = indicator_calculator.bollinger_bands(sample_ohlcv_data)
        
        assert isinstance(result, IndicatorResult)
        assert result.name == 'bb'
        assert 'upper' in result.metadata
        assert 'middle' in result.metadata
        assert 'lower' in result.metadata
        assert result.metadata['upper'] > result.metadata['middle']
        assert result.metadata['middle'] > result.metadata['lower']
    
    def test_stochastic_calculation(self, indicator_calculator, sample_ohlcv_data):
        """Test Stochastic indicator"""
        result = indicator_calculator.stochastic(sample_ohlcv_data)
        
        assert isinstance(result, IndicatorResult)
        assert result.name == 'stoch'
        assert 0 <= result.value <= 100
        assert 'k_percent' in result.metadata
        assert 'd_percent' in result.metadata
    
    def test_all_indicators_return_signals(self, indicator_calculator, sample_ohlcv_data):
        """Test all indicators return valid signals"""
        snapshot = indicator_calculator.calculate_all(sample_ohlcv_data, 'AAPL')
        
        for name, indicator in snapshot.indicators.items():
            assert isinstance(indicator.signal, SignalType)
            assert indicator.signal in [SignalType.BUY, SignalType.SELL, SignalType.HOLD,
                                       SignalType.STRONG_BUY, SignalType.STRONG_SELL]


# =====================
# RULE STRATEGY TESTS
# =====================

class TestRuleStrategy:
    """Test RuleStrategy"""
    
    def test_initialization(self, sample_strategy_rules):
        """Test strategy initializes with rules"""
        strategy = RuleStrategy(sample_strategy_rules)
        
        assert len(strategy.rules) == 3
        assert len(strategy.entry_rules) == 2
        assert len(strategy.exit_rules) == 1
    
    def test_rule_parsing(self, sample_strategy_rules):
        """Test rules parse correctly from config"""
        strategy = RuleStrategy(sample_strategy_rules)
        
        entry_rule = strategy.entry_rules[0]
        assert entry_rule.name == 'rsi_oversold'
        assert entry_rule.type == RuleType.ENTRY
        assert entry_rule.indicator == 'rsi'
        assert entry_rule.condition == 'less_than'
        assert entry_rule.value == 30
    
    def test_evaluate_entry_triggered(self, rule_strategy, sample_ohlcv_data,
                                     indicator_calculator):
        """Test entry evaluation when rules trigger"""
        snapshot = indicator_calculator.calculate_all(sample_ohlcv_data, 'AAPL')
        
        # Manually set RSI to oversold value
        snapshot.indicators['rsi'].value = 25  # < 30
        
        should_buy, confidence, rules = rule_strategy.evaluate_entry(snapshot)
        
        # Should trigger rsi_oversold rule
        assert 'rsi_oversold' in rules
    
    def test_evaluate_entry_not_triggered(self, rule_strategy, sample_ohlcv_data,
                                         indicator_calculator):
        """Test entry evaluation when no rules trigger"""
        snapshot = indicator_calculator.calculate_all(sample_ohlcv_data, 'AAPL')
        
        # Set RSI to non-triggering value
        snapshot.indicators['rsi'].value = 50
        snapshot.indicators['sma_20'].value = 90  # < 95 required
        
        should_buy, confidence, rules = rule_strategy.evaluate_entry(snapshot)
        
        # No rules should trigger
        assert should_buy == False
        assert confidence == 0.0
        assert len(rules) == 0
    
    def test_evaluate_exit_triggered(self, rule_strategy, sample_ohlcv_data,
                                    indicator_calculator):
        """Test exit evaluation when rules trigger"""
        snapshot = indicator_calculator.calculate_all(sample_ohlcv_data, 'AAPL')
        
        # Set RSI to overbought value
        snapshot.indicators['rsi'].value = 75  # > 70
        
        should_sell, rules = rule_strategy.evaluate_exit(snapshot)
        
        # Should trigger rsi_overbought rule
        assert 'rsi_overbought' in rules
        assert should_sell == True
    
    def test_evaluate_exit_not_triggered(self, rule_strategy, sample_ohlcv_data,
                                        indicator_calculator):
        """Test exit evaluation when no rules trigger"""
        snapshot = indicator_calculator.calculate_all(sample_ohlcv_data, 'AAPL')
        
        # Set RSI to non-triggering value
        snapshot.indicators['rsi'].value = 50
        
        should_sell, rules = rule_strategy.evaluate_exit(snapshot)
        
        # No rules should trigger
        assert should_sell == False
        assert len(rules) == 0
    
    def test_confidence_calculation(self, sample_strategy_rules):
        """Test confidence is calculated as % of rules triggered"""
        strategy = RuleStrategy(sample_strategy_rules)
        
        # Create mock snapshot
        class MockSnapshot:
            def __init__(self):
                self.indicators = {
                    'rsi': IndicatorResult('rsi', 25, SignalType.BUY, pd.Timestamp.now()),
                    'sma_20': IndicatorResult('sma_20', 96, SignalType.BUY, pd.Timestamp.now())
                }
        
        snapshot = MockSnapshot()
        should_buy, confidence, rules = strategy.evaluate_entry(snapshot)
        
        # Both rules trigger, so 2/2 = 100%
        assert should_buy == True
        assert confidence == 1.0
    
    def test_disabled_rules_ignored(self):
        """Test disabled rules don't trigger"""
        rules = [
            {
                'name': 'disabled_rule',
                'type': 'entry',
                'indicator': 'rsi',
                'condition': 'less_than',
                'value': 30,
                'enabled': False  # Disabled
            }
        ]
        
        strategy = RuleStrategy(rules)
        
        class MockSnapshot:
            def __init__(self):
                self.indicators = {
                    'rsi': IndicatorResult('rsi', 25, SignalType.BUY, pd.Timestamp.now())
                }
        
        snapshot = MockSnapshot()
        should_buy, confidence, rules_triggered = strategy.evaluate_entry(snapshot)
        
        # Disabled rule should not trigger
        assert should_buy == False
        assert len(rules_triggered) == 0


# =====================
# DECISION ENGINE TESTS
# =====================

class TestDecisionEngine:
    """Test DecisionEngine"""
    
    def test_initialization(self, decision_engine):
        """Test engine initializes correctly"""
        assert decision_engine is not None
        assert decision_engine.atr_multiplier_sl == 2.0
        assert decision_engine.atr_multiplier_tp == 3.0
    
    def test_make_buy_decision(self, decision_engine):
        """Test BUY decision generation"""
        context = DecisionContext(
            symbol='AAPL',
            current_price=150.0,
            atr=2.0,
            entry_triggered=True,
            entry_confidence=0.8,
            entry_rules=['rsi_oversold', 'price_above_sma20'],
            exit_triggered=False,
            exit_rules=[],
            all_signals={}
        )
        
        decision = decision_engine.make_decision(context)
        
        assert decision.symbol == 'AAPL'
        assert decision.decision == 'BUY'
        assert decision.confidence == 0.8
        assert decision.stop_loss == 150.0 - (2.0 * 2.0)  # price - (atr * 2)
        assert decision.take_profit == 150.0 + (2.0 * 3.0)  # price + (atr * 3)
    
    def test_make_sell_decision(self, decision_engine):
        """Test SELL decision generation"""
        context = DecisionContext(
            symbol='AAPL',
            current_price=150.0,
            atr=2.0,
            entry_triggered=False,
            entry_confidence=0.0,
            entry_rules=[],
            exit_triggered=True,
            exit_rules=['rsi_overbought'],
            all_signals={}
        )
        
        decision = decision_engine.make_decision(context)
        
        assert decision.symbol == 'AAPL'
        assert decision.decision == 'SELL'
        assert decision.confidence == 0.7  # Exit confidence is fixed
        assert decision.stop_loss == 150.0 + (2.0 * 2.0)  # Higher for short
        assert decision.take_profit == 150.0 - (2.0 * 3.0)  # Lower for short
    
    def test_make_hold_decision(self, decision_engine):
        """Test HOLD decision when no triggers"""
        context = DecisionContext(
            symbol='AAPL',
            current_price=150.0,
            atr=2.0,
            entry_triggered=False,
            entry_confidence=0.0,
            entry_rules=[],
            exit_triggered=False,
            exit_rules=[],
            all_signals={}
        )
        
        decision = decision_engine.make_decision(context)
        
        assert decision.decision == 'HOLD'
        assert decision.confidence == 0.0
        assert decision.stop_loss is None
        assert decision.take_profit is None
    
    def test_sl_tp_calculation_buy(self, decision_engine):
        """Test SL/TP calculation for BUY"""
        sl, tp = decision_engine._calculate_sl_tp(100.0, 2.0, 'BUY')
        
        assert sl == 100.0 - (2.0 * 2.0)  # 96.0
        assert tp == 100.0 + (2.0 * 3.0)  # 106.0
    
    def test_sl_tp_calculation_sell(self, decision_engine):
        """Test SL/TP calculation for SELL"""
        sl, tp = decision_engine._calculate_sl_tp(100.0, 2.0, 'SELL')
        
        assert sl == 100.0 + (2.0 * 2.0)  # 104.0
        assert tp == 100.0 - (2.0 * 3.0)  # 94.0
    
    def test_sl_tp_calculation_hold(self, decision_engine):
        """Test SL/TP calculation for HOLD"""
        sl, tp = decision_engine._calculate_sl_tp(100.0, 2.0, 'HOLD')
        
        assert sl is None
        assert tp is None


# =====================
# INTEGRATION TESTS
# =====================

class TestPhase2Integration:
    """Integration tests for Phase 2 (indicators → strategy → decision)"""
    
    def test_full_indicator_strategy_flow(self, indicator_calculator, rule_strategy,
                                         decision_engine, sample_ohlcv_data):
        """Test complete flow: indicators → rules → decision"""
        # Calculate indicators
        snapshot = indicator_calculator.calculate_all(sample_ohlcv_data, 'AAPL')
        
        # Evaluate strategy
        entry_triggered, entry_conf, entry_rules = rule_strategy.evaluate_entry(snapshot)
        exit_triggered, exit_rules = rule_strategy.evaluate_exit(snapshot)
        
        # Get ATR for SL/TP
        atr = snapshot.indicators['atr'].value
        current_price = float(sample_ohlcv_data['close'].iloc[-1])
        
        # Make decision
        context = DecisionContext(
            symbol='AAPL',
            current_price=current_price,
            atr=atr,
            entry_triggered=entry_triggered,
            entry_confidence=entry_conf,
            entry_rules=entry_rules,
            exit_triggered=exit_triggered,
            exit_rules=exit_rules,
            all_signals=snapshot.get_all_signals()
        )
        
        decision = decision_engine.make_decision(context)
        
        # Validate decision
        assert decision.symbol == 'AAPL'
        assert decision.decision in ['BUY', 'SELL', 'HOLD']
        assert 0.0 <= decision.confidence <= 1.0
    
    def test_multiple_symbols_processing(self, indicator_calculator, sample_ohlcv_data):
        """Test processing multiple symbols"""
        symbols = ['AAPL', 'MSFT', 'GOOGL']
        
        for symbol in symbols:
            snapshot = indicator_calculator.calculate_all(sample_ohlcv_data, symbol)
            
            assert snapshot.symbol == symbol
            assert len(snapshot.indicators) == 9
    
    def test_indicators_to_dict(self, indicator_calculator, sample_ohlcv_data):
        """Test indicator snapshot can be serialized to dict"""
        snapshot = indicator_calculator.calculate_all(sample_ohlcv_data, 'AAPL')
        snapshot_dict = snapshot.to_dict()
        
        assert 'symbol' in snapshot_dict
        assert 'timestamp' in snapshot_dict
        assert 'indicators' in snapshot_dict
        assert 'signals' in snapshot_dict


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
