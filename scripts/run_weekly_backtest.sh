#!/bin/bash
# Weekly Backtest Runner

cd /home/eric/.openclaw/workspace/AITradeAgent
source venv/bin/activate
mkdir -p logs

# Calculate dates (1 year ago to today)
START_DATE=$(date -d "1 year ago" +%Y-%m-%d)
END_DATE=$(date +%Y-%m-%d)

# Extract all symbols from config/finance.yaml
SYMBOLS=$(grep -A 200 "universe:" config/finance.yaml | grep -B 200 "data:" | grep "^    - " | awk '{print $2}' | tr -d "'" | sort -u | xargs)

if [ -z "$SYMBOLS" ]; then
    SYMBOLS="AAPL MSFT NVDA JNJ JPM XOM 0002.HK 0175.HK 0883.HK 0941.HK 1398.HK GFS MCHP MRVL MU NXPI UNH"
fi

echo "Running weekly backtest from $START_DATE to $END_DATE for symbols: $SYMBOLS"

# Run backtest
python3 -m finance_service.tools.backtest \
    --symbols $SYMBOLS \
    --start-date $START_DATE \
    --end-date $END_DATE \
    --strategy sma50_trend_regime > logs/weekly_backtest.log 2>&1

echo "Backtest completed."
