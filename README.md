# PicoClaw Trading Agent - picotradeagent

A sophisticated AI-powered trading assistant that integrates with PicoClaw framework, providing automated market analysis, trading signals, risk management, and portfolio tracking. Built on Flask backend with paper trading simulation and real-time market data via yfinance.

## Quick Start

### 1. Start the Finance Service

The Finance Service is the backend that handles all market data, analysis, and trading operations.

```bash
cd /home/eric/.picoclaw/workspace/picotradeagent
python3 run_finance_service.py
```

The service will start on `http://localhost:8801` and is ready to accept requests.

**Verify service is running:**
```bash
curl http://localhost:8801/health
```

Expected response: `{"service":"finance","status":"ok"}`

### 2. Key Entry Points

#### Finance Service (run_finance_service.py)
- **Purpose**: Main Flask backend for all trading operations
- **Runs on**: `http://localhost:8801`
- **Provides**: Market data, analysis, portfolio management, trade execution

#### PicoClaw Connector (picoclaw_connector.py)
- **Purpose**: Bridge between PicoClaw agents and Finance Service
- **Usage**: Import and use in PicoClaw agent definitions
- **Features**: Health checks, analysis, quotes, portfolio, performance, trade execution

## API Endpoints

### Health & Status
- **GET `/health`** - Service health check
  ```bash
  curl http://localhost:8801/health
  ```

### Market Data
- **GET `/quote/<symbol>`** - Get latest price quote
  ```bash
  curl http://localhost:8801/quote/AAPL
  ```

### Analysis
- **POST `/analyze/<symbol>`** - Full technical analysis
  ```bash
  curl -X POST http://localhost:8801/analyze \
    -H "Content-Type: application/json" \
    -d '{"symbol":"AAPL","lookback_days":60}'
  ```

### Portfolio Management
- **GET `/portfolio/state`** - Current portfolio status
  ```bash
  curl http://localhost:8801/portfolio/state
  ```

- **GET `/portfolio/performance`** - Portfolio performance metrics
  ```bash
  curl http://localhost:8801/portfolio/performance
  ```

- **POST `/portfolio/propose`** - Dry-run trade proposal validation
  ```bash
  curl -X POST http://localhost:8801/portfolio/propose \
    -H "Content-Type: application/json" \
    -d '{"symbol":"AAPL","action":"BUY","quantity":10,"confidence":0.85}'
  ```

- **POST `/portfolio/execute`** - Execute approved trade
  ```bash
  curl -X POST http://localhost:8801/portfolio/execute \
    -H "Content-Type: application/json" \
    -d '{"task_id":"123","approval_id":"user_approved_20260305"}'
  ```

## PicoClaw Integration

The picotradeagent is designed to work with PicoClaw agents. Use the `picoclaw_connector.py` module:

```python
from picoclaw_connector import get_connector

# Get connector instance
connector = get_connector()

# Check service health
if connector.health_check():
    print("Finance Service is running")

# Analyze a stock symbol
analysis = connector.analyze("AAPL")
print(f"Signal: {analysis['decision']}")

# Get quote
quote = connector.get_quote("AAPL")
print(f"Price: {quote['close']}")

# Propose a trade (validation only)
proposal = connector.propose_trade({
    "symbol": "AAPL",
    "action": "BUY",
    "quantity": 10,
    "confidence": 0.85
})

# Execute approved trade
result = connector.execute_trade(
    task_id="task_123",
    approval_id="user_approved_20260305"
)

# Get portfolio state
portfolio = connector.get_portfolio()
print(f"Cash: ${portfolio['cash']:.2f}")
print(f"Total Value: ${portfolio['total_value']:.2f}")

# Get performance metrics
perf = connector.get_performance()
print(f"Returns: {perf['total_return']:.2%}")
print(f"Sharpe: {perf['sharpe_ratio']:.2f}")
```

## System Architecture

```
picotradeagent/
├── run_finance_service.py      ← Main entry point
├── picoclaw_connector.py       ← Integration helper
│
├── finance_service/            ← Core backend
│   ├── app.py                  Main Flask application
│   ├── core/                   Configuration, logging, cache
│   ├── data/                   Market data providers
│   ├── indicators/             Technical analysis indicators
│   ├── strategies/             Trading strategy implementations
│   ├── brokers/                Broker configurations
│   ├── execution/              Trade execution engine
│   ├── risk/                   Risk management & validation
│   ├── portfolio/              Portfolio tracking & accounting
│   ├── storage/                Database interfaces
│   ├── dashboard/              Web UI components
│   └── ui/                     Frontend assets
│
├── picoclaw_config/            ← PicoClaw configuration
│   ├── finance_system_prompt.md
│   ├── finance_tool_policy.md
│   ├── router_rules.yaml
│   └── tool_schemas.json
│
├── config/                     ← Configuration files
├── tests/                      ← Unit and integration tests
├── doc/                        ← Documentation (all .md files except README)
└── storage/                    ← Runtime data (cache, databases, logs)
```

## Agent Skills

PicoClaw agents have access to the following skills via the Finance Service:

### Data Collection
- **data_agent_fetch** - Retrieve OHLCV market data for symbols

### Analysis
- **analysis_agent_indicators** - Calculate technical indicators (SMA, RSI, MACD, ATR, Bollinger)

### Strategy
- **strategy_agent_decide** - Generate BUY/SELL/HOLD signals with confidence scores

### Risk Management
- **risk_agent_validate** - Validate trades and calculate position sizing

### Execution
- **execution_agent_paper_trade** - Execute trades and update portfolio

### Learning
- **learning_agent_run** - Backtest strategies and optimize parameters

### Engine Control
- **engine_status** - Get portfolio status and metrics
- **engine_positions** - Get open positions with P&L
- **engine_trade_history** - Get trade records
- **engine_set_focus** - Set trading theme, region, or watchlist
- **engine_pause** - Pause automatic trading
- **engine_resume** - Resume after pause
- **engine_reset_portfolio** - Reset to initial cash
- **engine_last_report** - Get daily or learning reports

## Configuration

### Environment Variables
Set in `.env` or `picoclaw.env`:

```bash
# Finance Service
OPENBB_USE_YFINANCE=true
OPENBB_PROVIDER=yfinance
FINANCE_SERVICE_PORT=8801

# PicoClaw (AI Models & Channels)
OPENROUTER_API_KEY=your_key_here
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

# Telegram Integration
TELEGRAM_BOT_TOKEN=your_bot_token_here

# Slack Integration
SLACK_BOT_TOKEN=your_bot_token_here
SLACK_APP_TOKEN=your_app_token_here
```

### Configuration Files
- **config.json** - Main config in `~/.picoclaw/config.json`
- **Tool Definitions** - `picoclaw_config/tool_schemas.json`
- **Router Rules** - `picoclaw_config/router_rules.yaml`

## Common Tasks

### View Portfolio Status
```bash
curl http://localhost:8801/portfolio/state | python3 -m json.tool
```

### Get Latest Analysis
```bash
curl -X POST http://localhost:8801/analyze \
  -H "Content-Type: application/json" \
  -d '{"symbol":"NVDA","lookback_days":30}' | python3 -m json.tool
```

### Check Trading History
```bash
curl "http://localhost:8801/portfolio/trades?limit=10" | python3 -m json.tool
```

### Reset Portfolio to Initial State
```bash
curl -X POST http://localhost:8801/portfolio/reset | python3 -m json.tool
```

## Testing

Run tests to verify the system:

```bash
# Run all tests
python3 -m pytest tests/ -v

# Run specific test file
python3 -m pytest tests/test_finance_service.py -v

# Run with coverage
python3 -m pytest tests/ --cov=finance_service
```

## Monitoring

The Finance Service logs to:
- **Console**: Direct output to terminal
- **File**: `finance_service.log` in project root
- **SQLite DB**: `storage/finance.db` for trade logs

Check status:
```bash
# View logs
tail -f finance_service.log

# Check running process
ps aux | grep run_finance_service

# Monitor port
netstat -tuln | grep 8801
```

## Project Structure

- **run_finance_service.py** - Service launcher (START HERE)
- **picoclaw_connector.py** - Agent integration library
- **finance_service/** - Core backend implementation
- **picoclaw_config/** - PicoClaw integration configuration
- **tests/** - Test suite and validation scripts
- **doc/** - Documentation (development notes, architecture, planning)
- **config/** - Configuration defaults
- **storage/** - Runtime data storage (databases, caches, logs)

## Troubleshooting

### Service won't start
```bash
# Check if port 8801 is already in use
lsof -i :8801

# Kill existing process
pkill -f run_finance_service

# Start fresh
python3 run_finance_service.py
```

### Connection refused when accessing from another machine
```bash
# Check firewall rules
sudo ufw status

# If needed, allow port 8801
sudo ufw allow 8801/tcp
```

### Data caching issues
```bash
# Clear cache
rm -rf storage/cache/*

# Restart service
pkill -f run_finance_service
python3 run_finance_service.py
```

## Performance Tips

1. **Use caching** - Market data is cached to reduce API load
2. **Batch requests** - Request multiple symbols in single queries when possible
3. **Adjust lookback** - Use shorter lookback_days for faster analysis
4. **Monitor logs** - Check `finance_service.log` for performance bottlenecks

## Security

- ✅ Paper trading only - No real money at risk
- ✅ API validation - All inputs validated
- ✅ Error isolation - Errors don't crash the service
- ✅ Audit logging - All trades logged with timestamps
- ✅ Rate limiting - Built-in request throttling

## Support

For issues or questions:
1. Check logs: `tail -f finance_service.log`
2. Verify service health: `curl http://localhost:8801/health`
3. Review configuration in `~/.picoclaw/config.json`
4. Test endpoints manually with curl
5. Check documentation in `doc/` folder

## License

MIT License - See LICENSE file for details
