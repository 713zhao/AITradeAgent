# AITradeAgent

AI-powered trading assistant for market scanning, signal generation, risk checks, and paper-trade execution.

## Minimal Startup

Install dependencies:

```bash
pip install -r requirements.txt
```

Start service:

```bash
./start.sh
```

Or run in foreground:

```bash
python3 finance_service/run_finance_service.py
```

Health check:

```bash
curl http://127.0.0.1:8801/health
```

Detailed startup docs: [docs/STARTUP.md](docs/STARTUP.md)

## Manual Market Scan Trigger

Trigger a scan (normal mode, market-hours enforced):

```bash
curl "http://127.0.0.1:8801/trigger?trigger_type=market-scan&market=US"
```

Trigger a scan with debug bypass (run even when market closed):

```bash
curl "http://127.0.0.1:8801/trigger?trigger_type=market-scan&market=US&debug_bypass_market_hours=true"
```

Trigger using last Friday as analysis date:

```bash
curl "http://127.0.0.1:8801/trigger?trigger_type=market-scan&market=US&debug_bypass_market_hours=true&debug_last_friday=true"
```

Trigger with explicit date:

```bash
curl "http://127.0.0.1:8801/trigger?trigger_type=market-scan&market=US&debug_bypass_market_hours=true&as_of_date=2026-04-24"
```

Check latest scan metadata:

```bash
curl http://127.0.0.1:8801/api/scan/last | python3 -m json.tool
```

## Key Endpoints

```bash
# Health
curl http://127.0.0.1:8801/health

# Quote
curl http://127.0.0.1:8801/quote/AAPL

# Analyze
curl -X POST http://127.0.0.1:8801/analyze \
  -H "Content-Type: application/json" \
  -d '{"symbol":"AAPL","lookback_days":60}'

# Portfolio state
curl http://127.0.0.1:8801/portfolio/state

# Portfolio performance
curl http://127.0.0.1:8801/portfolio/performance

# Trading history (all trades)
curl http://127.0.0.1:8801/api/trades/history

# Filter by period: today | this_week | this_month | this_year
curl "http://127.0.0.1:8801/api/trades/history?period=today"
curl "http://127.0.0.1:8801/api/trades/history?period=this_week"
curl "http://127.0.0.1:8801/api/trades/history?period=this_month"
curl "http://127.0.0.1:8801/api/trades/history?period=this_year"

# Filter by specific date
curl "http://127.0.0.1:8801/api/trades/history?date=2026-04-27"

# Filter by symbol and/or side
curl "http://127.0.0.1:8801/api/trades/history?symbol=AAPL&side=BUY"

# Combine filters (e.g. this month, BUY only, max 50 results)
curl "http://127.0.0.1:8801/api/trades/history?period=this_month&side=BUY&limit=50"
```

Response includes `filter`, `summary` (count/buys/sells/total_trade_value) and a `trades` list.

## Project Layout

```text
AITradeAgent/
├── start.sh
├── requirements.txt
├── config/
├── docs/
├── finance_service/
│   ├── run_finance_service.py
│   └── app.py
├── scripts/
│   ├── tools/
│   ├── tests/
│   ├── backtest/
│   ├── setup/
│   ├── integration/
│   └── ops/
├── tests/
└── logs/
```

## Common Commands

```bash
# Run tests
pytest tests/ -v

# Tail runtime log (when started by start.sh)
tail -f logs/finance_service_restart.log

# Stop service
pkill -f run_finance_service.py
```

## Notes

- The project uses a single dependency file: `requirements.txt`.
- `start.sh` writes PID to `logs/finance.pid`.
- Scan summaries are sent to Telegram when Telegram config is enabled.
