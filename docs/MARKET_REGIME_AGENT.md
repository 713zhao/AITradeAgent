# MarketRegimeAgent

**File:** `finance_service/agents/market_regime_agent.py`  
**Agent ID:** `market_regime_agent`  
**Goal:** Provide market-wide context for symbol selection and risk management.

---

## Overview

`MarketRegimeAgent` analyzes five major US market indices to assess the current risk regime, trend strength, and volatility environment. Its output is consumed by `SymbolSelectorAgent` to weight candidate symbols with macro-aware context.

---

## Data Model

### `IndexMetrics` (per index)

| Field | Type | Description |
|---|---|---|
| `symbol` | str | Ticker symbol (e.g. `^GSPC`) |
| `name` | str | Display name (e.g. `S&P 500`) |
| `price` | float | Latest closing price |
| `change_pct_1d` | float | 1-day % change |
| `change_pct_5d` | float | 5-day % change |
| `vs_sma20_pct` | float | % distance from 20-day SMA |
| `vs_sma50_pct` | float | % distance from 50-day SMA |
| `vs_sma200_pct` | float | % distance from 200-day SMA |
| `ytd_return` | float | Year-to-date return % |
| `volume_ratio_vs_20d` | float | Volume vs 20-day average |

### `MarketBreadth`

| Field | Type | Description |
|---|---|---|
| `advancers_ratio` | float | Fraction of symbols advancing (0–1) |
| `new_highs_20d` | int | Symbols at 20-day highs |
| `new_lows_20d` | int | Symbols at 20-day lows |
| `volume_ratio_vs_avg` | float | Market-wide volume ratio |
| `symbols_above_sma20_pct` | float | % symbols above their SMA20 |
| `symbols_above_sma50_pct` | float | % symbols above their SMA50 |

### `MarketRegime` (output)

| Field | Type | Description |
|---|---|---|
| `risk_on` | bool | `True` = risk-on environment |
| `momentum_favoring` | bool | `True` = momentum stocks favored |
| `volatility_regime` | str | `"low"` / `"normal"` / `"high"` |
| `trend_strength` | str | `"weak"` / `"moderate"` / `"strong"` |
| `summary` | str | Human-readable regime description |
| `indices` | dict | `IndexMetrics` for each index as dict |
| `breadth` | dict | `MarketBreadth` as dict (may be empty) |

---

## Tracked Indices

| Key | Symbol | Name |
|---|---|---|
| `SP500` | `^GSPC` | S&P 500 |
| `NASDAQ` | `^IXIC` | NASDAQ Composite |
| `DOW` | `^DJI` | Dow Jones Industrial |
| `VIX` | `^VIX` | CBOE Volatility Index |
| `RUSSELL2000` | `^RUT` | Russell 2000 |

---

## Regime Derivation Logic

### Trend Strength (from SP500 vs SMA200)

| SP500 vs SMA200 | `trend_strength` | `risk_on` effect |
|---|---|---|
| > +2% | `"strong"` | unchanged |
| −2% to +2% | `"moderate"` | unchanged |
| < −2% | `"weak"` | → `False`, momentum → `False` |

### Volatility Regime (from VIX)

| VIX Level | `volatility_regime` | `risk_on` effect |
|---|---|---|
| > 30 | `"high"` | → `False` |
| 15–30 | `"normal"` | unchanged |
| < 15 | `"low"` | unchanged |

### Momentum (from NASDAQ 1D change)

| NASDAQ 1D Change | `momentum_favoring` |
|---|---|
| > +1% | `True` |
| < −1% | `False`, `risk_on` → `False` |

### Breadth (from watchlist scanner, if available)

| Advancers Ratio | Effect |
|---|---|
| < 45% | `risk_on` → `False`, `momentum_favoring` → `False` |
| > 65% | no change (bullish note in summary) |

---

## Caching

- **Agent-level in-memory cache:** 60-minute TTL (configurable)
- **DataAgent SQLite cache:** 1-day OHLCV data cached by symbol+interval
- `force_refresh: True` in payload bypasses agent-level cache

---

## Configuration (`config/finance.yaml`)

```yaml
market_regime_agent:
  cache_ttl_minutes: 60
  indices:
    SP500:
      symbol: "^GSPC"
      name: "S&P 500"
    NASDAQ:
      symbol: "^IXIC"
      name: "NASDAQ Composite"
    DOW:
      symbol: "^DJI"
      name: "Dow Jones Industrial"
    VIX:
      symbol: "^VIX"
      name: "CBOE Volatility Index"
    RUSSELL2000:
      symbol: "^RUT"
      name: "Russell 2000"
```

---

## Usage

```python
agent = MarketRegimeAgent(config_engine, data_agent, market_scanner=None)
report = await agent.run({"force_refresh": True})
print(report.payload["regime"]["summary"])
# → "Risk-on regime: SP500 vs SMA200: 1.2%; VIX normal at 18.4"
```

---

## Known Issues / Notes

| Issue | Status | Details |
|---|---|---|
| SMA200 requires 200+ trading days | ✅ Fixed | Lookback set to 300 calendar days |
| `KeyError: 'close'` from DataAgent | ✅ Fixed | Columns normalized to lowercase after fetch |
| NaN guard for SMA if insufficient rows | ✅ Fixed | Returns `0.0` when SMA is NaN (safe fallback) |
| Market breadth is placeholder | ⚠️ Partial | Returns hardcoded `0.60` advancers_ratio; real computation not yet implemented |

---

## Related Agents

- **`SymbolSelectorAgent`** — consumes `MarketRegime` as market context for LLM prompt
- **`MacroNewsAgent`** — provides news context alongside regime context
- **`DataAgent`** — fetches OHLCV data for all 5 indices
