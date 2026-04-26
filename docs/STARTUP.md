# Startup Guide

This project now keeps a minimal root startup surface.

## Start the service

Use either of these two entrypoints from the project root:

1. `./start.sh`
2. `python3 finance_service/finance_service/run_finance_service.py`

The service runs on `http://127.0.0.1:8801`.

## Verify

```bash
curl http://127.0.0.1:8801/health
```

Expected:

```json
{"status":"ok"}
```

## Trigger a debug market scan (last Friday)

```bash
curl "http://127.0.0.1:8801/trigger?trigger_type=market-scan&market=US&debug_bypass_market_hours=true&debug_last_friday=true"
```

Check latest scan metadata:

```bash
curl http://127.0.0.1:8801/api/scan/last
```
