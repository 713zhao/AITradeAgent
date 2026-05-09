#!/bin/bash
# Start AiTradeAgent in paper trading mode with sma50_trend_regime

cd "$(dirname "$0")"
source venv/bin/activate

echo "Starting Finance Service Orchestrator..."
echo "Strategy: sma50_trend_regime (regime-filtered SMA50)"
echo "Mode: Paper Trading (no real money)"
echo ""
echo "Logs will output to stdout. Press Ctrl+C to stop."
echo "---

python -m finance_service.main --config config/finance.yaml
