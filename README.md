# PicoClaw Finance Agent

A sophisticated trading assistant that integrates PicoClaw with OpenBB market data, technical analysis, and paper trading simulation. Built for Raspberry Pi compatibility with strict safety guardrails.

## Features

✅ **Market Data & Fundamentals** - Real-time prices, historical OHLCV, income statements, balance sheets
✅ **Technical Analysis** - RSI, MACD, SMA, ATR, Bollinger Bands, Stochastic (no LLM hallucination)
✅ **Rule-Based Strategy** - Trend + momentum filtering with configurable parameters
✅ **Risk Management** - Position sizing, stop-loss, max drawdown constraints
✅ **Paper Portfolio** - Simulated trading with realistic slippage and accounting
✅ **Human Approval Gate** - Telegram/Slack notifications before trade execution
✅ **Audit Logging** - SQLite persistence of all runs, trades, and portfolio snapshots
✅ **Caching Layer** - Intelligent data caching to reduce OpenBB API load

## Architecture

```
finance_service/          Python backend with tools & simulation
  ├── app.py             Main Flask service + orchestrator
  ├── core/               Config, logging, cache, data models
  ├── tools/              OpenBB wrappers, indicators, risk tools
  ├── strategies/         Baseline rule-based strategy
  ├── sim/                Portfolio, execution, metrics
  └── storage/            SQLite DBs (cache, runs, trades)

picoclaw_config/          Prompts, router rules, tool schemas
  ├── finance_system_prompt.md      System instructions for LLM
  ├── finance_tool_policy.md        Tool usage constraints
  ├── router_rules.yaml             Intent routing rules
  └── tool_schemas.json             OpenAPI-style tool definitions
```

## Installation

### Requirements
- Python 3.8+
- pip
- Virtual environment (recommended)

### Steps

1. **Clone or navigate to project**
   ```bash
   cd /home/eric/.picoclaw/workspace/picotradeagent
   ```

2. **Create virtual environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **(Optional) Configure Approval Gate**
   
   Set environment variables for Telegram or Slack:
   ```bash
   export TELEGRAM_BOT_TOKEN="your_token"
   export TELEGRAM_CHAT_ID="your_chat_id"
   # OR
   export SLACK_BOT_TOKEN="your_token"
   export SLACK_CHANNEL="#trading"
   ```

## Quick Start

### 1. Start Finance Service

```bash
python -m finance_service.app
```

Service runs on `http://localhost:5000`

### 2. Test Analysis via CLI

```bash
python -m tests.test_analysis AAPL
```

### 3. Test Portfolio Simulation

```bash
python -m tests.test_portfolio
```

## API Reference

### Health Check
```
GET /health
→ {"status": "ok", "service": "finance"}
```

### Analyze Symbol
```
POST /analyze
Content-Type: application/json

{
  "symbol": "TSLA"
}

→ {
  "task_id": "uuid",
  "symbol": "TSLA",
  "decision": "BUY",
  "confidence": 0.75,
  "signals": {
    "trend": "up",
    "rsi": 65.0,
    "sma50": 175.50
  },
  "position": {
    "action_qty": 10,
    "action_value": 1850.00
  },
  "risk": {
    "risk_level": "medium",
    "max_loss_estimate": 150.00,
    "stop_loss": 175.00,
    "take_profit": 195.00
  },
  "required_approval": true
}
```

### Get Portfolio State
```
GET /portfolio/state
→ {
  "cash": 98150.00,
  "equity": 18500.00,
  "total_value": 116650.00,
  "positions": {
    "TSLA": {
      "qty": 10,
      "current_price": 185.00,
      "market_value": 1850.00,
      "unrealized_pnl": 50.00
    }
  }
}
```

### Propose Trade
```
POST /portfolio/propose
Content-Type: application/json

{
  "task_id": "uuid-from-analyze",
  "symbol": "TSLA",
  "decision": "BUY",
  "position": {"action_qty": 10, "action_value": 1850}
}

→ {
  "valid": true,
  "summary": "BUY 10 TSLA @ $185.00",
  "details": {...}
}
```

### Execute Trade (requires approval)
```
POST /portfolio/execute
Content-Type: application/json

{
  "task_id": "uuid-from-propose",
  "approval_id": "approval-uuid"
}

→ {
  "success": true,
  "message": "Bought 10 shares of TSLA @ $185.00",
  "portfolio_state": {...}
}
```

### Get Quote
```
GET /quote/AAPL
→ {
  "symbol": "AAPL",
  "price": 175.50,
  "data": {...}
}
```

## Configuration

Edit [finance_service/core/config.py](finance_service/core/config.py) to customize:

```python
# Risk Constraints
MAX_POSITION_SIZE = 0.20          # 20% per symbol
MAX_EXPOSURE = 0.90               # 90% total stocks
MAX_DAILY_LOSS = 0.03             # 3% daily stop
MAX_DRAWDOWN = 0.10               # 10% drawdown stop

# Initial Capital
DEFAULT_INITIAL_CASH = 100000      # $100k paper trading

# Strategy
STRATEGY_TYPE = "baseline_rule"    # Changeable in v2
```

## Strategy Details

### Baseline Rule Strategy

Combines trend + momentum filtering:

**Entry (BUY):**
- Price > SMA(50) + 2% (uptrend)
- RSI(14) between 45-70 (momentum without overbought)
- Position size via ATR-based risk (1% portfolio risk)

**Exit (SELL):**
- Price < SMA(50) - 2% (downtrend)
- RSI(14) > 75 (overbought)
- Stop-loss at ATR * 2 below entry

**Confidence Scoring:**
- Each signal contributes 0.1-0.3 to confidence
- Max 1.0, displayed as decision certainty

## Tools - Never Hallucinate

The LLM (PicoClaw) **must call these tools**; never compute indicators in-text:

### Data Tools
- `get_price_historical(symbol, start, end)` - OHLCV candles
- `get_fundamentals(symbol, statement)` - Income/balance/cashflow
- `get_company_profile(symbol)` - Sector, industry, etc.
- `get_quote(symbol)` - Latest price + bid/ask

### Indicator Tools
- `calc_rsi(prices, period)` - Relative Strength Index
- `calc_macd(prices)` - MACD + signal
- `calc_sma(prices, window)` - Simple Moving Average
- `calc_atr(highs, lows, closes)` - Average True Range

### Risk Tools
- `calc_position_size(symbol, price, atr)` - Returns qty, stop-loss
- `validate_trade(symbol, action, qty, price)` - Check constraints

### Portfolio Tools
- `portfolio_get_state()` - Current positions + cash
- `propose_trade(decision)` - Dry-run validation
- `execute_trade(task_id, approval_id)` - Execute after approval
- `portfolio_get_performance()` - Returns, Sharpe, drawdown

## Safety Guardrails

### Hard Constraints
1. **No real money** - Paper trading only
2. **Human approval** - All trades must be approved (YES/NO)
3. **Position sizing** - Max 20% per stock, 90% total exposure
4. **Drawdown limit** - 10% max, halts trading
5. **Daily loss** - 3% max daily stop loss
6. **No fabrication** - All prices/returns from tools only

### Error Handling
- If OpenBB data unavailable → "insufficient data"
- If validation fails → Explain constraint + suggest adjustment
- If tool timeout → Retry 3x, then fail gracefully

## Testing

### Unit Tests
```bash
python -m pytest tests/ -v
```

### Integration Test (Full Flow)
```bash
python -m tests.test_end_to_end
```

### Manual Test with Flask
```bash
# Terminal 1: Start service
python -m finance_service.app

# Terminal 2: Test endpoint
curl -X POST http://localhost:5000/analyze \
  -H "Content-Type: application/json" \
  -d '{"symbol": "AAPL"}'
```

## Logging & Auditing

All activity logged to SQLite:

**Runs Database** (`storage/runs.sqlite`)
- task_id, symbol, decision_json, timestamp, approval status

**Trade Log**
- task_id, symbol, action, quantity, price, approval_id, executed_at

**Portfolio Snapshots**
- timestamp, cash, equity, positions snapshot

Query example:
```python
from finance_service.core.logging import RunLogger

logger = RunLogger()
run = logger.get_run("task-uuid")
trades = logger.get_trades("task-uuid")
```

## Integration with PicoClaw

### Step 1: Register Tools
In PicoClaw config, expose Finance Service tools:

```yaml
tools:
  - name: analyze_symbol
    endpoint: http://localhost:5000/analyze
    auth: none
  - name: proposal_trade
    endpoint: http://localhost:5000/portfolio/propose
    auth: approval_token
```

### Step 2: Load Finance Prompts
PicoClaw detects finance intent and loads:
- `picoclaw_config/finance_system_prompt.md` → system message
- `picoclaw_config/tool_schemas.json` → tool definitions
- `picoclaw_config/router_rules.yaml` → routing logic

### Step 3: Route Messages
If message contains ticker + action:
→ Finance mode activated
→ Access to all tools above
→ LLM follows strict tool-first policy

### Example Conversation

**User:** "Analyze TSLA"
**PicoClaw:** [Calls `/analyze` with TSLA]
→ Returns decision: BUY with 75% confidence

**PicoClaw:** "I recommend **BUY 10 shares of TSLA at $185** (confidence: 75%). Risk assessment: max loss $150 with stop at $175. This requires approval."

**User:** "YES"
**PicoClaw:** [Calls `/portfolio/propose` → `/portfolio/execute`]
→ "Trade executed: Bought 10 TSLA @ $185.00. New portfolio value: $116,650"

## Roadmap (v2)

- [ ] Multiple strategies (mean-reversion, momentum, pairs)
- [ ] Backtesting engine with performance reports
- [ ] Options support (Greeks, volatility surface)
- [ ] Multi-timeframe analysis
- [ ] Sentiment indicators (news + social)
- [ ] Portfolio rebalancing automation
- [ ] Risk attribution & contribution analysis
- [ ] Real brokerage integration (Alpaca, TD Ameritrade)

## Known Limitations

1. **Simulated prices only** - Uses last close; no intraday fills
2. **Slippage assumed flat** - 0.05% fixed; real markets vary
3. **No market hours validation** - Trades assumed market is open
4. **Single-leg trades** - No spreads, only simple buy/sell (options later)
5. **No portfolio financing** - Can't short (yet)

## Support & Troubleshooting

### OpenBB Connection Issues
```
Error: "No data available for SYMBOL"
Solution: Verify ticker symbol is correct (AAPL, not APPLE)
```

### Database Locked
```
Error: "database is locked"
Solution: Close other Finance Service instances; SQLite has limited concurrency
```

### Approval Timeout
```
Error: "Approval timeout after 300s"
Solution: Respond with YES/NO within timeout window
```

## License

MIT - Use freely for research and non-commercial purposes

## Authors

Built with PicoClaw + OpenBB

---

**Last Updated:** March 2026
**Version:** 0.1.0 (Alpha)
