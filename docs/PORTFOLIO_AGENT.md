# PortfolioAgent - Specification & Design

**Agent ID:** `portfolio_agent`  
**File:** `finance_service/agents/portfolio_agent.py`  
**Status:** ✅ Production-ready, actively used  
**Version:** 1.0  
**Last Updated:** 2026-03-29

---

## Overview

PortfolioAgent is the **single source of truth** for portfolio state: positions, cash balance, equity, and realized P&L. It persists trades to SQLite and calculates real‑time metrics when requested. It also reacts to `TRADE_EXECUTED` events to update positions.

**Key Responsibility:** Maintain accurate, consistent portfolio records and provide historical performance data.

---

## Design Philosophy

```
                    ┌─────────────────────────────────┐
                    │  TRADE_EXECUTED event            │
                    │  payload: execution_result       │
                    └──────────────┬──────────────────┘
                                   │
                    ┌──────────────▼─────────────────┐
                    │  PortfolioAgent.handle_trade_   │
                    │      executed(trade_info)       │
                    │  - Validate fields             │
                    │  - Create Trade object         │
                    │  - Update positions (avg cost) │
                    │  - Adjust cash                 │
                    │  - Persist to SQLite           │
                    └──────────────┬─────────────────┘
                                   │
                    ┌──────────────▼─────────────────┐
                    │  GET_PORTFOLIO_STATE request    │
                    │  → get_detailed_portfolio_state│
                    │  → returns full metrics dict   │
                    └─────────────────────────────────┘
```

---

## Input Parameters & Events

### Handles Events

- `TRADE_EXECUTED` → `handle_trade_executed(trade_info)`
- `GET_PORTFOLIO_STATE` → `get_detailed_portfolio_state(chat_id=None)`

### `get_detailed_portfolio_state(chat_id: Optional[str] = None) -> AgentReport`

Returns a payload with:

```python
{
  "timestamp": "2026-03-29T09:30:00",
  "positions": {
    "NVDA": {"quantity": 10, "avg_cost": 150.25, "current_price": 151.50, "market_value": 1515.0},
    ...
  },
  "cash": 63883.86,
  "equity_metrics": {
    "total_equity": 102954.04,
    "unrealized_pnl": 2954.04,
    "total_return_pct": 2.954,
    "drawdown_pct": 0.0,
    "sharpe_ratio": null,  # not computed here
    "max_drawdown_pct": 0.0,
  },
  "trade_count": 25,
  "latest_trade": {...}
}
```

---

## Underlying Models

- **Trade**: `(trade_id, symbol, side, quantity, price, commission, status, timestamp, decision, confidence, reason)`
- **Position**: `(symbol, quantity, avg_cost, current_price, opened_at, updated_at, trades: list, metadata: dict)`
  - **Note:** `entry_price` is an alias for `avg_cost` (property getter/setter) to maintain compatibility with broker-style code. `to_dict()` includes both `avg_cost` and `entry_price` fields.
- **Portfolio**: aggregate of positions + cash.

`TradeRepository` handles persistence and portfolio calculation (`calculate_portfolio(initial_cash)`).

---

## Data Persistence

Database: `finance_service/storage/portfolio.sqlite`

Tables:
- `trades`: all executed trades (immutable)
- `positions`: current open positions (updated on each trade)
- `equity_snapshots`: optional periodic equity snapshots (for performance metrics)

`TradeRepository` uses `sqlite3` with JSON blobs for trade details.

---

## Position Update Logic

For BUY:
- New position if not exists; otherwise increase quantity and recalc average cost:  
  `new_avg = (old_qty * old_avg + new_qty * price) / (old_qty + new_qty)`
- Subtract `quantity * price` from cash (plus commission if nonzero)
- `entry_price` set to the fill price (alias of `avg_cost`)

For SELL:
- Reduce quantity; if quantity reaches 0, remove position.
- Add `quantity * price` to cash.
- Realized P&L = `(price - avg_cost) * quantity` (affects equity; cash reflects proceeds).

---

## Query Payload Structure

`get_detailed_portfolio_state()` returns:

```python
{
  "timestamp": "2026-03-29T09:30:00",
  "positions": {
    "NVDA": {
      "symbol": "NVDA",
      "quantity": 10,
      "avg_cost": 150.25,
      "entry_price": 150.25,   # alias, same as avg_cost
      "current_price": 151.50,
      "market_value": 1515.0,
      "cost_basis": 1502.5,
      "unrealized_pnl": 12.5,
      "unrealized_pnl_pct": 0.0083,
      "opened_at": "...",
      "updated_at": "...",
      "trades": [...],
      "metadata": {}
    },
    ...
  },
  "equity_metrics": {
    "total_equity": 102614.69,
    "cash": 63883.86,
    "net_position_value": 38730.83,
    "gross_position_value": 38730.83,
    "unrealized_pnl": 2614.69,
    "realized_pnl": 0.0,
    "total_pnl": 2614.69,
    "total_return_pct": 2.6147,
    "drawdown_pct": 0.0,
    "max_drawdown_pct": 0.0,
    "position_count": 5,
    "trade_count": 22,
    "win_rate": 0.0
  }
}
```

---

## Recent Fixes (2026-03-31)

- **Position corruption:** Added `entry_price` property alias to `Position` model. `to_dict()` now includes `entry_price`. Fixed NaN equity caused by missing entry price when other code accessed `position['entry_price']`.
- **Equity guard:** `Position.market_value()` returns 0.0 for invalid `current_price` (NaN, None, infinite).
- **Price validation:** `PortfolioAgent.update_prices_from_data_agent()` validates fetched prices (must be numeric, non-NaN, >0) before updating.
- **Endpoint:** Added `/portfolio/performance` route to expose `equity_metrics` (mirrors `/api/dashboard/performance`).

These changes resolved a 13-hour production outage and stabilized portfolio reporting.

---

## Configuration

```yaml
finance:
  portfolio:
    initial_cash: 100000.0
    commission_per_share: 0.0
    slippage_pct: 0.0  # optional, not applied
```

---

## Event Flow Integration

```
TRADE_EXECUTED
    ↓
PortfolioAgent.handle_trade_executed()
    ↓
Update positions/cash → commit to DB
    ↓
Publish PORTFOLIO_UPDATE event (optional)
    ↓
HealthAgent may query get_detailed_portfolio_state
TelegramAgent uses it for /portfolio command
```

---

## Query Methods

- `get_portfolio_summary()` → quick equity + positions count
- `get_position(symbol)` → single Position
- `get_trades(limit=None)` → recent trades
- `get_detailed_portfolio_state()` → full payload as above

---

## Error Handling

- Missing `trade_info` fields → `AgentReport(status="error")`.
- Cash check: if insufficient, BUY is rejected (error).
- On database errors → logs and returns error; does not crash service.

---

## Testing

Test suite: `tests/test_portfolio_agent.py` covers:
- Basic trade execution (BUY/SELL)
- Average cost calculation
- Cash updates
- Position lifecycle

Run:
```bash
cd /home/eric/.openclaw/workspace/AITradeAgent
source venv/bin/activate
python -m pytest tests/test_portfolio_agent.py -v
```

---

## Notes

- PortfolioAgent is the **only agent that writes** to the database; all other agents are read-only.
- Repository is currently synchronous; needs async wrapper for production.
- Snapshot-based equity calculation can be expensive; caching is advisable.
- Future: add equity snapshots periodically to enable performance metrics without recomputing full history.

---

**Summary:** PortfolioAgent maintains the authoritative portfolio state, processes trades, and provides real-time metrics to the rest of the system.
