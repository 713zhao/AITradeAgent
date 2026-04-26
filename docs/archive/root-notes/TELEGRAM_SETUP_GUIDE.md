# Telegram Setup - Detailed Guide

## Bot Token Configuration
Your bot token is already configured:
- Token: `8694519756:AAGxp6d7Fho3-696h4ae4tHvjcVmtazQUOw`
- Location: `config/finance.yaml`

## Step 1: Get Your Chat ID

### Using Setup Script (Recommended)
```bash
cd /home/claw.zhao/.openclaw/workspace/AITradeAgent
source .venv/bin/activate
python3 setup_telegram.py
```

In Telegram:
1. Find your bot
2. Send ANY message (Hi, Hello, etc.)
3. Bot responds with Chat ID
4. Copy the Chat ID (just numbers)
5. Press Ctrl+C to exit

## Step 2: Configure Chat ID

Edit `config/finance.yaml`:

Find:
```yaml
notifications:
  telegram:
    bot_token: "8694519756:AAGxp6d7Fho3-696h4ae4tHvjcVmtazQUOw"
    chat_id: ""
```

Replace with:
```yaml
    chat_id: "123456789"  # Your Chat ID
```

## Step 3: Verify & Restart

```bash
# Test configuration
python3 test_telegram_config.py

# Restart service
pkill -f "run_finance_service.py"
python3 run_finance_service.py
```

## Notifications You'll Receive

- **Trade Executed**: BUY/SELL with prices and confidence
- **Position Closed**: With profit/loss details
- **Error Alerts**: Critical issues
- **Daily Summary**: End-of-day statistics

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Bot doesn't respond | Wait 30s, retry (rate limits) |
| Chat ID not showing | Verify target bot in Telegram |
| Messages not arriving | Check Chat ID format (numeric only) |
| Connection errors | Review logs: `tail -f logs/finance_service.log | grep telegram` |

## Support
See `TELEGRAM_BOT_CONFIGURATION.md` for more details.
