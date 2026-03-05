# Quick Start Guide - PicoClaw Finance Agent

## 5-Minute Setup

```bash
# 1. Navigate to project
cd /home/eric/.picoclaw/workspace/picotradeagent

# 2. Run setup script
bash setup.sh

# 3. Start service
source venv/bin/activate
python -m finance_service.app
# → Service ready on http://localhost:5000

# 4. In another terminal, test
python -m tests.test_analysis AAPL
```

## Key Files to Know

| File | What It Does |
|------|--------------|
| `finance_service/app.py` | Main service (run this!) |
| `finance_service/core/config.py` | Adjust risk limits here |
| `finance_service/strategies/baseline_rule_strategy.py` | Customize strategy |
| `picoclaw_config/finance_system_prompt.md` | LLM instructions |
| `.env` | Set Telegram/Slack tokens |

## Using the Service

### Via REST API
```bash
# Analyze a stock
curl -X POST http://localhost:5000/analyze \
  -H "Content-Type: application/json" \
  -d '{"symbol": "TSLA"}'

# Get portfolio
curl http://localhost:5000/portfolio/state
```

### Via Python
```python
from finance_service.app import finance_service

# Analyze
result = finance_service.analyze("AAPL")
print(f"Decision: {result['decision']}")

# Trade
if result['decision'] != 'HOLD':
    proposal = finance_service.portfolio_propose_trade(result)
    if proposal['valid']:
        # Approve → execute
        exec_result = finance_service.portfolio_execute_trade(
            result['task_id'], 
            approval_id="auto"
        )
        print(f"Executed: {exec_result['message']}")
```

## Approval Methods

### Manual (Default)
- No setup needed
- Prompts in console during test
- Use for development

### Telegram
```bash
# Set environment
export TELEGRAM_BOT_TOKEN="your_bot_token"
export TELEGRAM_CHAT_ID="your_chat_id"

# Restart service
python -m finance_service.app
# → Trade proposals sent via Telegram
```

### Slack
```bash
# Set environment
export SLACK_BOT_TOKEN="xoxb-your-token"
export SLACK_CHANNEL="#trading"

# Restart service
python -m finance_service.app
# → Trade proposals posted to Slack
```

## Customizing Risk Policy

Edit `finance_service/core/config.py`:

```python
MAX_POSITION_SIZE = 0.20      # 20% per stock (change to 0.10 for 10%)
MAX_EXPOSURE = 0.90           # 90% total stocks in portfolio
MAX_DAILY_LOSS = 0.03         # Stop after 3% daily loss
MAX_DRAWDOWN = 0.10           # Stop after 10% peak-to-trough loss
DEFAULT_INITIAL_CASH = 100000 # Starting capital for paper trading
```

## Trading Strategy

The baseline rule strategy:
- **BUY** when: Price > SMA(50) AND RSI(14) between 45-70
- **SELL** when: Price < SMA(50) OR RSI(14) > 75
- **Position size** based on ATR (volatility-scaled)

Customize in `baseline_rule_strategy.py`:
```python
self.sma_window = 50          # Trend period
self.rsi_window = 14          # Momentum period
self.rsi_buy_high = 70        # Overbought threshold
self.rsi_sell_high = 75       # Exit threshold
```

## Monitoring Activity

### View all trades
```bash
sqlite3 finance_service/storage/runs.sqlite
SELECT task_id, symbol, decision_json FROM runs ORDER BY created_at DESC;
```

### Check portfolio history
```bash
SELECT * FROM portfolio_snapshots ORDER BY created_at DESC LIMIT 10;
```

## Troubleshooting

**"No data available"**
- Symbol doesn't exist or market is closed
- Check spelling (e.g., AAPL not APPLE)

**"Approval timeout"**
- Respond YES/NO within 5 minutes
- Extend timeout in config.py

**"database is locked"**
- Close other instances
- Delete `finance_service/storage/` if stuck, restart

**"OpenBB connection error"**
- OpenBB API may be down
- System uses mock data fallback automatically

## Testing Checklist

- [ ] Service starts: `python -m finance_service.app`
- [ ] Health check: `curl http://localhost:5000/health`
- [ ] Analysis works: `python -m tests.test_analysis AAPL`
- [ ] Portfolio sim works: `python -m tests.test_portfolio`
- [ ] Full flow works: `python -m tests.test_end_to_end`
- [ ] Approval gate works (manual mode)

## Integration with PicoClaw

1. **Register tools** - In PicoClaw config, add Finance Service endpoint
2. **Load prompts** - PicoClaw loads finance_system_prompt.md on finance intent
3. **Route messages** - "analyze AAPL" → Finance mode
4. **Execute trades** - approval_gate handles YES/NO responses

Example in PicoClaw config:
```yaml
contexts:
  finance:
    system_prompt: ./picoclaw_config/finance_system_prompt.md
    tools_base: http://localhost:5000
    tool_schemas: ./picoclaw_config/tool_schemas.json
    auto_activate: finance_keywords | ticker_pattern
```

## Common Commands

```bash
# Start fresh
source venv/bin/activate
python -m finance_service.app

# Test analysis
python -m tests.test_analysis TSLA

# Check logs
tail -f /tmp/finance_service.log

# Query trades
sqlite3 finance_service/storage/runs.sqlite

# Reset portfolio
# (Delete storage/runs.sqlite and restart)

# Update risk policy
# (Edit core/config.py and restart)
```

## Key Concepts

### Confidence Score (0.0-1.0)
- How certain the strategy is about the decision
- Higher = stronger signals
- Used for position sizing adjustment

### Risk Level (low/medium/high)
- low: < $50 max loss
- medium: $50-500 max loss
- high: > $500 max loss

### Signals
- **trend**: up/down/flat (SMA comparison)
- **rsi**: 0-100 momentum indicator
- **atr**: volatility measure (used for stops)

### PnL Tracking
- **Realized PnL**: From closed trades
- **Unrealized PnL**: From open positions
- **Total PnL**: Sum of both

## Next Steps

1. **Customize** risk limits for your portfolio size
2. **Test** with small amounts first
3. **Monitor** audit logs for all activity
4. **Adjust** strategy parameters based on results
5. **Plan** backtest runs to validate strategy
6. **Integrate** with PicoClaw for production

---

**Ready to trade?** Start the service and test with your first stock!

```bash
python -m finance_service.app
# Then: curl -X POST http://localhost:5000/analyze -H "Content-Type: application/json" -d '{"symbol": "AAPL"}'
```

**Questions?** Check README.md for full documentation.
