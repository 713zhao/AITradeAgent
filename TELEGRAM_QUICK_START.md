# Telegram Bot - Quick Start

## 3 Simple Steps

### 1. Get Chat ID (Run once)
```bash
python3 setup_telegram.py
# Send any message to bot in Telegram
# Copy the Chat ID shown in response
```

### 2. Update Configuration
Edit `config/finance.yaml`:
```yaml
notifications:
  telegram:
    bot_token: "8694519756:AAGxp6d7Fho3-696h4ae4tHvjcVmtazQUOw"
    chat_id: "YOUR_CHAT_ID"  # Replace with your number
```

### 3. Restart Service
```bash
pkill -f "run_finance_service.py"
python3 run_finance_service.py
```

## Test
```bash
python3 test_telegram_config.py
```

## Done! ✅
You'll now receive trading notifications.
