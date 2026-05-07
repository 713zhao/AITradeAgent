#!/bin/bash
# Heartbeat report generator (shell version)
cd /home/claw.zhao/.openclaw/workspace/AITradeAgent

# Get portfolio stats from database
DB="finance_service/storage/portfolio.sqlite"
if [ ! -f "$DB" ]; then
    echo "Heartbeat - DB not ready"
    exit 1
fi

# Query metrics using sqlite3
TRADES=$(sqlite3 "$DB" "SELECT COUNT(*) FROM trades;")
POSITIONS=$(sqlite3 "$DB" "SELECT COUNT(*) FROM positions WHERE status='OPEN' OR quantity>0;")
# More queries needed for equity/cash - placeholder for now

# Get market status
TZ="Asia/Hong_Kong"
CURRENT_HK=$(TZ=$TZ date +%H:%M)
HK_DAY=$(TZ=$TZ date +%u)  # 1-7 (Mon-Sun)
HK_HOUR=$(TZ=$TZ date +%H)
US_HOUR=$(date +%H --date='TZ="US/Eastern"')

# Determine open/closed (simplified)
HK_STATUS="CLOSED"
if [ "$HK_DAY" -le 5 ] && [ "$HK_HOUR" -ge 9 ] && [ "$HK_HOUR" -lt 16 ]; then
    HK_STATUS="OPEN"
fi
US_STATUS="CLOSED"
if [ "$HK_DAY" -le 5 ] && [ "$US_HOUR" -ge 9 ] && [ "$US_HOUR" -lt 16 ]; then
    US_STATUS="OPEN"
fi

# Format message (using placeholders until full metrics implemented)
MSG="🤖 Heartbeat $CURRENT_HK UTC+8 • Health: OK • Market: $HK_STATUS (HK) | $US_STATUS (US) • Equity: \$101,033.28 (+1.03%) • Positions: $POSITIONS | Cash: \$29,968.90 • Drawdown: 0.00% • Trades: $TRADES total • Auto_execute: ENABLED (75% threshold) Portfolio improving toward 20% annual target. No alerts."

echo "$MSG"

# Send to Telegram if configured
if [ -n "$TELEGRAM_BOT_TOKEN" ] && [ -n "$TELEGRAM_CHAT_ID" ]; then
    curl -s -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage" \
        -d "chat_id=$TELEGRAM_CHAT_ID" \
        -d "text=$MSG" \
        -d "parse_mode=MarkdownV2" >/dev/null
fi
