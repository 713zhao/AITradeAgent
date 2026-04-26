#!/bin/bash
# Start AITradeAgent with environment from .env

cd /home/claw.zhao/.openclaw/workspace/AITradeAgent

# Load .env if exists
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Stop any existing instance
pkill -f "run_finance_service.py" 2>/dev/null
fuser -k 8801/tcp 2>/dev/null 2>/dev/null

# Start service
.venv/bin/python finance_service/run_finance_service.py > logs/finance_service_restart.log 2>&1 &
echo $! > logs/finance.pid
echo "Started PID $(cat logs/finance.pid)"
