# AnalysisAgent - Specification & Design

**Agent ID:** `analysis_agent`  
**File:** `finance_service/agents/analysis_agent.py`  
**Status:** ✅ Production-ready, actively used  
**Version:** 2.0  
**Last Updated:** 2026-03-29

---

## Overview

AnalysisAgent transforms raw OHLCV data into a rich set of technical indicators and signals. It is the **quantitative engine** that computes momentum, trend, volatility, and regime metrics used by the StrategyAgent.

**Key Responsibility:** Produce a standardized `IndicatorsSnapshot` for any symbol given its historical data.

---

## Design Philosophy

```
                    ┌─────────────────────────────────┐
                    │  DATA_FETCH_COMPLETE event       │
                    │  payload: {dataframe, ...}       │
                    └──────────────┬──────────────────┘
                                   │
                    ┌──────────────▼─────────────────┐
                    │  AnalysisAgent.run(data_payload,│
                    │                      symbol)    │
                    │  - Reconstruct DataFrame       │
                    │  - Compute 10+ indicators      │
                    │  - Generate signals (BUY/SELL/ │
                    │    HOLD) per indicator         │
                    └──────────────┬─────────────────┘
                                   │
                    ┌──────────────▼─────────────────┐
                    │  ANALYSIS_COMPLETE event        │
                    │  payload: IndicatorsSnapshot   │
                    └─────────────────────────────────┘
```

---

## Input Parameters

### `run(data_payload: Dict[str, Any], symbol: str) -> Optional[AgentReport]`

- `data_payload`: The `Event.data` from `DATA_FETCH_COMPLETE`. Must contain a `'dataframe'` key with a list of OHLCV records. Optionally includes `'fundamentals'`.
- `symbol`: The symbol being analyzed (for logging and snapshot labeling).

Returns an `AgentReport` where `payload` is an `IndicatorsSnapshot`:

```python
{
    "symbol": "NVDA",
    "timestamp": "2026-03-29T14:30:00",
    "current_price": 150.25,
    "indicators": {
        "rsi": {"name": "rsi", "value": 42.65, "signal": "HOLD", "metadata": {}},
        "macd": {"name": "macd", "value": 1.23, "signal": "BUY", "metadata": {"histogram": 0.45}},
        "sma_20": {"name": "sma_20", "value": 148.50, "signal": "BUY", "metadata": {}},
        "sma_50": {"name": "sma_50", "value": 145.20, "signal": "HOLD", "metadata": {}},
        "sma_200": {"name": "sma_200", "value": 140.10, "signal": "BUY", "metadata": {}},
        "ema_12": {...},
        "ema_26": {...},
        "atr": {...},
        "bb": {...},
        "stoch": {...},
        "regime_score": {"name": "regime_score", "value": 0.78, "signal": "BULL", "metadata": {}}
    }
}
```

Each `IndicatorResult` includes:
- `name`: indicator name
- `value`: numeric value
- `signal`: `"BUY"`, `"SELL"`, `"HOLD"` (or regime labels like `"BULL"`, `"BEAR"`)
- `metadata`: additional computed fields (e.g., MACD histogram, BB bandwidth)

---

## Indicator Catalog

| Indicator | Period(s) | Signal Logic | Output Fields |
|-----------|-----------|--------------|---------------|
| RSI | 14 | `>70` → SELL; `<30` → BUY; else HOLD | `value`, `signal` |
| MACD | fast=12, slow=26, signal=9 | MACD line crosses above signal → BUY; below → SELL | `value`, `signal`, `histogram` |
| SMA | 20, 50, 200 | Price above SMA → BUY; below → SELL | `value`, `signal` |
| EMA | 12, 26 | Similar to SMA, faster | `value`, `signal` |
| ATR | 14 | Volatility measure (no direction) | `value` (signal always HOLD) |
| Bollinger Bands | 20, 2σ | Price below lower band → BUY; above upper → SELL | `upper`, `lower`, `width`, `signal` |
| Stochastic | %K=14, %D=3 | %K crosses above %D → BUY; below → SELL | `k`, `d`, `signal` |
| Regime Score | composite | Multi-factor score [-1,1] → BULL/BEAR/NEUTRAL | `value`, `signal` (`BULL`/`BEAR`/`NEUTRAL`) |

---

## Internal Methods

- `_calculate_all(df, symbol, fundamentals=None)` orchestrates computation.
- `_calculate_rsi(df, period=14)`
- `_calculate_macd(df, fast=12, slow=26, signal=9)`
- `_calculate_sma(df, periods=[20,50,200])`
- `_calculate_ema(df, periods=[12,26])`
- `_calculate_atr(df, period=14)`
- `_calculate_bollinger_bands(df, period=20, std=2)`
- `_calculate_stochastic(df, k_period=14, d_period=3)`
- `_calculate_regime_score(df)`: Composite of RSI, SMA, MACD signals.

---

## Configuration

Indicator periods are configurable via `analysis_agent` section:

```yaml
finance:
  analysis_agent:
    rsi_period: 14
    macd_fast: 12
    macd_slow: 26
    macd_signal: 9
    sma_periods: [20, 50, 200]
    ema_periods: [12, 26]
    atr_period: 14
    bb_period: 20
    bb_std: 2.0
    stoch_k: 14
    stoch_d: 3
```

(Not yet fully wired; code currently uses `_default_periods()`.)

---

## Event Flow Integration

```
DATA_FETCH_COMPLETE (data_payload)
    ↓
AnalysisAgent.run(data_payload, symbol)
    ↓
ANALYSIS_COMPLETE published
    ↓
Orchestrator calls StrategyAgent.run(indicators_snapshot)
```

---

## Error Handling

- Missing or insufficient data (less than required lookback) → returns `AgentReport(status="error")` with descriptive message.
- Individual indicator failures are logged; other indicators still computed.
- If fundamentals are needed but missing, regime_score falls back to technical-only.

---

## Testing

Test suite: `tests/test_analysis_agent.py`

Run:
```bash
cd /home/eric/.openclaw/workspace/AITradeAgent
source venv/bin/activate
python -m pytest tests/test_analysis_agent.py -v
```

---

## Notes

- AnalysisAgent is stateless; it operates purely on the provided DataFrame.
- It expects DataFrame index to be datetime and columns to include `open`, `high`, `low`, `close`, `volume` (case insensitive).
- The `IndicatorsSnapshot` is the core data structure consumed by all strategy implementations.
  - As of 2026-03-31, `IndicatorsSnapshot` supports `.get(key, default=None)` for dict-like access, allowing compatibility with code expecting plain dicts (e.g., ExitAgent).
- Future: Add additional indicators (e.g., ADX, Parabolic SAR) as needed.

---

## Recent Fixes (2026-03-31)

| Fix | Description |
|-----|-------------|
| IndicatorsSnapshot.get() | Added `get()` method to `IndicatorsSnapshot` model. Enables dict-like access (`indicators.get('rsi')`) to return indicator numeric values. This fixed AttributeError crashes in ExitAgent's strategic degradation checks. |

---


**Summary:** AnalysisAgent is a pure function from OHLCV → indicators. It is a critical, well-tested component used by every strategy.
