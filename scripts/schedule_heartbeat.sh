#!/bin/bash
# Cron job for AITradeAgent heartbeat reports
# Runs every 30 minutes during market hours

cd /home/claw.zhao/.openclaw/workspace/AITradeAgent
source .venv/bin/activate 2>/dev/null || true

# Run heartbeat report
python3 scripts/heartbeat_report.py --send >> logs/heartbeat.log 2>&1
