# Phase 6.2 Action Plan: Advanced Order Types
**Status**: Planned  
**Created**: March 4, 2026  
**Timeline**: 3 Days  
**Current Phase**: Phase 6.2 (Advanced Order Types)

---

## Phase 6.2 Overview

**Objective**: Implement advanced order types beyond basic market and limit orders to provide sophisticated trading capabilities.

**Inputs**: BrokerManager from Phase 6.1 with basic order support
**Outputs**: Advanced order types with full lifecycle management

**Key Components**:
- Trailing Stop orders
- OCO (One Cancels Other) orders  
- Bracket orders (profit target + stop loss)
- Iceberg orders (partial fill management)

---

## Task Breakdown (3 Days)

### DAY 1: Trailing Stop Orders

#### Task 6.2.1: Trailing Stop Engine (`finance_service/brokers/advanced_orders/trailing_stop.py`)
- Implement trailing stop logic with distance-based and percentage-based trailing
- Handle price movements and stop level updates
- Support both BUY and SELL trailing stops
- Track highest/lowest prices for trailing calculation
- **Checklist**:
  - [ ] File created (200 lines)
  - [ ] Distance-based trailing (fixed dollar amount)
  - [ ] Percentage-based trailing (relative percentage)
  - [ ] BUY/SELL trailing stop support
  - [ ] State management (active, triggered, filled)

#### Task 6.2.2: Trailing Stop Integration
- Add trailing stop support to PaperBroker and AlpacaBroker
- Update OrderType enum to include TRAILING_STOP
- Implement trailing stop validation and processing
- **Checklist**:
  - [ ] OrderType.TRAILING_STOP added
  - [ ] PaperBroker supports trailing stops
  - [ ] AlpacaBroker supports trailing stops
  - [ ] Validation logic implemented

### DAY 2: OCO & Bracket Orders

#### Task 6.2.3: OCO Order Manager (`finance_service/brokers/advanced_orders/oco_manager.py`)
- Implement One-Cancels-Other order logic
- Handle order linking and dependency management
- Support multiple OCO pairs (A cancels B, B cancels A)
- Track OCO group status and execution
- **Checklist**:
  - [ ] File created (180 lines)
  - [ ] Order linking mechanism
  - [ ] Cancellation propagation logic
  - [ ] OCO group state management
  - [ ] Support for complex OCO chains

#### Task 6.2.4: Bracket Order Engine (`finance_service/brokers/advanced_orders/bracket_orders.py`)
- Implement bracket orders (entry + profit target + stop loss)
- Handle three-order group (entry, TP, SL)
- Support OCO for TP/SL cancellation
- Track bracket group execution and P&L
- **Checklist**:
  - [ ] File created (220 lines)
  - [ ] Entry order placement logic
  - [ ] Profit target order setup
  - [ ] Stop loss order setup
  - [ ] Bracket group management

#### Task 6.2.5: Advanced Order Validation
- Implement validation for all advanced order types
- Add parameter validation (trailing distances, bracket ratios)
- Handle edge cases and error conditions
- **Checklist**:
  - [ ] Trailing stop validation
  - [ ] OCO validation logic
  - [ ] Bracket order validation
  - [ ] Error handling and recovery

### DAY 3: Iceberg Orders & Integration

#### Task 6.2.6: Iceberg Order Implementation (`finance_service/brokers/advanced_orders/iceberg_orders.py`)
- Implement iceberg order logic (partial fills)
- Handle hidden quantity disclosure
- Track remaining hidden quantity
- Support time-based and fill-based disclosure
- **Checklist**:
  - [ ] File created (160 lines)
  - [ ] Hidden quantity tracking
  - [ ] Disclosure logic (time/fill-based)
  - [ ] Iceberg state management
  - [ ] Partial fill handling

#### Task 6.2.7: Advanced Order Integration (`finance_service/brokers/broker_manager.py`)
- Update BrokerManager to support all advanced order types
- Add advanced order routing and processing
- Implement advanced order event handling
- Update order tracking and reporting
- **Checklist**:
  - [ ] BrokerManager advanced order methods
  - [ ] Event system updates
  - [ ] Order tracking enhancements
  - [ ] Reporting improvements

#### Task 6.2.8: Unit Tests
- Create comprehensive tests for all advanced order types
- Test integration with existing broker system
- Validate edge cases and error conditions
- **Checklist**:
  - [ ] Trailing stop tests (15 tests)
  - [ ] OCO order tests (12 tests)
  - [ ] Bracket order tests (10 tests)
  - [ ] Iceberg order tests (8 tests)
  - [ ] Integration tests (10 tests)
  - [ ] All 55 tests passing

---

## Advanced Order Types

### 1. Trailing Stop Orders

**Purpose**: Automatically adjust stop price as price moves favorably

**Types**:
- **Distance-based**: Fixed dollar amount trailing
- **Percentage-based**: Fixed percentage trailing

**Logic**:
```
For SELL trailing stop:
- Stop price starts at initial level
- As price increases, stop price increases by trailing amount
- When price decreases and hits stop price → trigger order

For BUY trailing stop:
- Stop price starts at initial level  
- As price decreases, stop price decreases by trailing amount
- When price increases and hits stop price → trigger order
```

**Configuration**:
```python
OrderRequest(
    symbol="AAPL",
    side=OrderSide.SELL,
    quantity=100,
    order_type=OrderType.TRAILING_STOP,
    trailing_distance=2.0,  # $2.00 trailing
    trailing_type="distance"  # or "percentage"
)
```

### 2. OCO (One Cancels Other) Orders

**Purpose**: Execute one order and automatically cancel the other

**Use Case**: 
- Set profit target AND stop loss simultaneously
- If profit target hits → cancel stop loss
- If stop loss hits → cancel profit target

**Logic**:
```
Order Group: [Profit Target Order, Stop Loss Order]
- When one order fills → cancel the other
- Track group status and dependencies
- Support complex OCO chains
```

**Configuration**:
```python
# Create OCO group
oco_group = OCOGroup([
    OrderRequest(...profit_target...),
    OrderRequest(...stop_loss...)
])
```

### 3. Bracket Orders

**Purpose**: Single order that creates a complete trading setup (entry + TP + SL)

**Components**:
- **Entry Order**: Initial position entry
- **Profit Target**: Exit when target reached
- **Stop Loss**: Exit when loss limit reached

**Logic**:
```
1. Place entry order
2. When filled → automatically place TP and SL orders
3. TP and SL form OCO group
4. When either TP or SL fills → cancel the other
```

**Configuration**:
```python
BracketOrder(
    entry_order=OrderRequest(...),
    profit_target=OrderRequest(...),
    stop_loss=OrderRequest(...)
)
```

### 4. Iceberg Orders

**Purpose**: Execute large orders by revealing only a portion at a time

**Types**:
- **Time-based**: Reveal hidden quantity after time intervals
- **Fill-based**: Reveal hidden quantity after partial fills

**Logic**:
```
Hidden Quantity = Total Quantity - Displayed Quantity
- Display smaller portion to market
- When displayed portion fills → reveal more
- Continue until all hidden quantity executed
```

**Configuration**:
```python
IcebergOrder(
    total_quantity=10000,
    displayed_quantity=1000,  # Show 1000, hide 9000
    disclosure_type="time",   # or "fill"
    disclosure_interval=60    # seconds for time-based
)
```

---

## Architecture

### File Structure

```
finance_service/brokers/advanced_orders/
├── __init__.py
├── trailing_stop.py          (200 lines)
├── oco_manager.py           (180 lines)
├── bracket_orders.py        (220 lines)
└── iceberg_orders.py        (160 lines)
```

### Integration Points

```
BrokerManager
├── Basic Orders (Phase 6.1)
│   ├── Market orders
│   ├── Limit orders
│   └── Stop orders
└── Advanced Orders (Phase 6.2)
    ├── Trailing stops
    ├── OCO orders
    ├── Bracket orders
    └── Iceberg orders
```

### Event System Updates

**New Event Types**:
- `TRAILING_STOP_UPDATED`: Stop level adjusted
- `OCO_TRIGGERED`: One order in OCO group filled
- `BRACKET_ENTRY_FILLED`: Bracket entry order filled
- `ICEBERG_PORTION_FILLED`: Iceberg portion executed

---

## Success Criteria

- [ ] Trailing stop orders implemented and working
- [ ] OCO order groups functional
- [ ] Bracket orders create complete trading setups
- [ ] Iceberg orders handle partial execution
- [ ] All advanced orders integrate with existing broker system
- [ ] 55/55 tests passing
- [ ] Zero regressions from Phase 6.1
- [ ] Performance: Order processing < 10ms for advanced orders

---

## Test Strategy

### Test Coverage (55 tests total)

**Trailing Stop Tests (15 tests)**:
- Distance-based trailing (BUY/SELL)
- Percentage-based trailing (BUY/SELL)
- Stop level updates
- Order triggering
- Edge cases (rapid price movements)

**OCO Tests (12 tests)**:
- Basic OCO pair execution
- OCO chain support
- Cancellation propagation
- Group state management
- Error handling

**Bracket Tests (10 tests)**:
- Entry order placement
- TP/SL automatic creation
- OCO integration
- Group lifecycle
- P&L tracking

**Iceberg Tests (8 tests)**:
- Hidden quantity tracking
- Time-based disclosure
- Fill-based disclosure
- Partial execution
- Completion handling

**Integration Tests (10 tests)**:
- BrokerManager integration
- Event system integration
- Portfolio integration
- Performance tests
- Regression tests

---

## Configuration Updates

### Extended OrderType Enum

```python
class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    TRAILING_STOP = "trailing_stop"
    OCO = "oco"
    BRACKET = "bracket"
    ICEBERG = "iceberg"
```

### Advanced Order Parameters

```yaml
finance:
  advanced_orders:
    trailing_stop:
      max_distance: 50.0  # Maximum trailing distance
      min_distance: 0.01  # Minimum trailing distance
    oco_orders:
      max_group_size: 10  # Maximum orders in OCO group
      timeout_seconds: 3600  # OCO group timeout
    bracket_orders:
      min_profit_target_pct: 1.0  # Minimum profit target %
      max_stop_loss_pct: 20.0     # Maximum stop loss %
    iceberg_orders:
      min_display_ratio: 0.01     # Minimum display ratio (1%)
      max_display_ratio: 0.50     # Maximum display ratio (50%)
```

---

## Dependencies

- ✅ Phase 6.1: BrokerManager with basic order support
- ✅ Phase 5: ExecutionEngine for order processing
- ✅ Phase 3: Portfolio Manager for position tracking
- ✅ EventBus: For advanced order event handling

---

## Performance Targets

| Order Type | Processing Time | Memory Usage | Event Latency |
|------------|----------------|--------------|---------------|
| Trailing Stop | < 5ms | < 1KB | < 1ms |
| OCO Orders | < 10ms | < 2KB | < 2ms |
| Bracket Orders | < 15ms | < 3KB | < 3ms |
| Iceberg Orders | < 8ms | < 2KB | < 2ms |

---

## Risk Management

### Advanced Order Risks
- **Trailing Stops**: Market gap risk, slippage on trigger
- **OCO Orders**: Partial fill scenarios, cancellation timing
- **Bracket Orders**: Entry failure, TP/SL synchronization
- **Iceberg Orders**: Information leakage, execution timing

### Mitigation Strategies
- Order validation and parameter limits
- Event-driven processing for reliability
- Comprehensive error handling and recovery
- Performance monitoring and alerting

---

## Next Steps

After Phase 6.2 completion:
1. **Phase 6.3**: Additional Brokers (IBKR, TD Ameritrade)
2. **Phase 6.4**: Real-time Market Data (WebSocket)
3. **Phase 6.5**: Order Optimization (Smart routing)
4. **Phase 7**: Backtesting Engine

---

## Summary

Phase 6.2 implements sophisticated order types that enable professional trading strategies:

- **Trailing Stops**: Dynamic stop loss management
- **OCO Orders**: Risk-reward optimization
- **Bracket Orders**: Complete trade setup automation
- **Iceberg Orders**: Large order execution

This builds on the broker foundation from Phase 6.1 and prepares for advanced trading strategies in subsequent phases.