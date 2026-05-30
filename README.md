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

## Service Management

The service is started via `start.sh` (nohup background process, not systemd).

```bash
# Start
./start.sh

# Stop
pkill -f run_finance_service.py

# Restart
pkill -f run_finance_service.py; sleep 2; ./start.sh

# Check if running
ps aux | grep run_finance_service

# Tail runtime log
tail -f finance_service.out
```

## Health Watchdog

An external liveness watchdog polls `/health` every 5 minutes and sends a Telegram alert on failure, attempting an auto-restart before alerting:

```
~/.openclaw/workspace/heartbeat_check.py
```

It runs as a background loop (started separately from the finance service):

```bash
# Check if watchdog is running
ps aux | grep heartbeat_check

# Start watchdog manually
python3 ~/.openclaw/workspace/heartbeat_check.py --loop --interval-minutes 5
```

## Common Commands

```bash
# Run tests
pytest tests/ -v

# Tail runtime log
tail -f logs/finance_service_restart.log

# Manual stop (prefer systemctl stop when systemd is managing the service)
pkill -f run_finance_service.py
```

## Notes

- The project uses a single dependency file: `requirements.txt`.
- `start.sh` writes PID to `logs/finance.pid`. Use `systemctl --user restart aitrade.service` instead when systemd is managing the service.
- Scan summaries are sent to Telegram when Telegram config is enabled.

## Hourly Portfolio Report

A background daemon automatically generates and sends hourly portfolio reports while any market is open.

**What's included:**
- Current equity, cash position, and P&L
- Open positions with unrealized gains/losses
- Strategy performance assessment (vs. 20% CAGR, 1.0 Sharpe ratio targets)
- Recommended actions based on backtest metrics
- Data freshness indicator
- Telegram notifications (optional)

**How it works:**
- `scripts/progress_monitor_daemon.py` — background scheduler process
- `scripts/heartbeat_report.py` — generates the rich portfolio report
- Runs every 60 minutes during market hours (HK: 09:00-16:00, US: 09:00-16:00 ET)

**Manual test:**
```bash
python3 scripts/heartbeat_report.py
```

**Troubleshooting:**
If the hourly report stops working, the most common cause is **merge conflicts** in `scripts/heartbeat_report.py`. This manifests as import/syntax errors. To fix:
1. Check file for git merge markers: `grep -n "<<<<<<< HEAD\|=======\|>>>>>>> master" scripts/heartbeat_report.py`
2. Resolve conflicts, keeping the richer version from the `master` branch
3. Verify syntax: `python3 -m py_compile scripts/heartbeat_report.py`
4. Test: `python3 scripts/heartbeat_report.py`
