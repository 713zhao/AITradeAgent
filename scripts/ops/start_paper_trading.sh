#!/bin/bash
# Start AiTradeAgent in paper trading mode with sma50_trend_regime

cd "$(dirname "$0")"
source venv/bin/activate

export OPENBB_USE_YFINANCE=true
export OPENBB_PROVIDER=yfinance
export FLASK_ENV=production
export PYTHONUNBUFFERED=1
export LOG_LEVEL=INFO

echo "=========================================="
echo "AiTradeAgent - Paper Trading"
echo "Strategy: sma50_trend_regime"
echo "Mode: Paper (no real money)"
echo "=========================================="
echo ""

python3 finance_service/run_finance_service.py
