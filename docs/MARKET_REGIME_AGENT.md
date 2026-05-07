# MarketRegimeAgent

**File:** `finance_service/agents/market_regime_agent.py`  
**Agent ID:** `market_regime_agent`  
**Goal:** Provide market-wide context for symbol selection and risk management.

---

## Overview

`MarketRegimeAgent` analyzes market indices to assess the current risk regime, trend strength, and volatility environment. It supports **dual-market analysis**: US indices (S&P 500, NASDAQ, Dow Jones) and Hong Kong indices (Hang Seng, H-Shares, Shanghai Composite). Regional regime reports are generated independently via `_derive_regime(market="HK"|"US")`, and a combined risk-off flag is computed (risk-off = either market in risk-off state). Output is consumed by `SymbolSelectorAgent` (market-specific) and ExitAgent (combined regime) to weight candidate symbols with macro-aware context.

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

### US Market Indices

| Key | Symbol | Name | Market |
|---|---|---|---|
| `SP500` | `^GSPC` | S&P 500 | US |
| `NASDAQ` | `^IXIC` | NASDAQ Composite | US |
| `DOW` | `^DJI` | Dow Jones Industrial | US |
| `VIX` | `^VIX` | CBOE Volatility Index | US |
| `RUSSELL2000` | `^RUT` | Russell 2000 | US |

### Hong Kong Market Indices

| Key | Symbol | Name | Market |
|---|---|---|---|
| `HSI` | `^HSI` | Hang Seng Index | HK |
| `HSCE` | `^HSCE` | H-Shares Index | HK |
| `SHANGHAI` | `000001.SS` | Shanghai Composite | HK |
| `VHSI` | `^VHSI` | CBOE Hang Seng VIX | HK |

---

## Regime Derivation Logic

### Per-Market Regime Computation

When `_derive_regime(market="HK"|"US")` is called:

- **US Regime**: Uses SP500/VIX/NASDAQ indices
- **HK Regime**: Uses HSI/VHSI/HSCE indices  
- **Combined Regime**: Risk-off if **either** US or HK is risk-off; momentum-off if either is momentum-off

### Trend Strength (Primary Index vs SMA200)

| Primary Index vs SMA200 | `trend_strength` | `risk_on` effect |
|---|---|---|
| > +2% | `"strong"` | unchanged |
| −2% to +2% | `"moderate"` | unchanged |
| < −2% | `"weak"` | → `False`, momentum → `False` |

### Volatility Regime (from VIX / VHSI)

| Index / Level | `volatility_regime` | `risk_on` effect |
|---|---|---|
| **US VIX** > 30 or **VHSI** > 30 | `"high"` | → `False` |
| 15–30 | `"normal"` | unchanged |
| < 15 | `"low"` | unchanged |

### Momentum (from NASDAQ 1D change or HSI 1D change)

| Primary Index 1D Change | `momentum_favoring` |
|---|---|
| > +1% | `True` |
| < −1% | `False`, `risk_on` → `False` |

**Note:** Uses NASDAQ for US regime, HSI for HK regime.

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

## Agent Report Structure

The output `AgentReport.payload` contains:

```json
{
  "regime": { ... },          // Combined risk-off flag
  "regime_us": { ... },       // US-only regime (SP500/VIX/NASDAQ)
  "regime_hk": { ... },       // HK-only regime (HSI/VHSI/HSCE)
  "indices": { ... },         // IndexMetrics for all 9 indices
  "breadth": { ... },         // Market breadth data (if available)
  "timestamp": "2026-04-04T..."
}
```

Each regime object includes: `risk_on`, `momentum_favoring`, `volatility_regime`, `trend_strength`, `summary`.

---
## Related Agents

- **`SymbolSelectorAgent`** — consumes per-market `regime_us` or `regime_hk` + combined `regime` for LLM prompt
- **`MacroNewsAgent`** — provides regional news context (US or HK sources) alongside regime context
- **`ExitAgent`** — uses combined regime for position exit decisions
- **`DataAgent`** — fetches OHLCV data for all 9 indices
