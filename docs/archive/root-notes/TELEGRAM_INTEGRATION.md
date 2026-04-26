# Telegram Integration Architecture

## System Flow

```
ExecutionAgent → Publishes Event
    ↓
EventBus
    ↓
TelegramAgent (Listen)
    ↓
TelegramNotificationService
    ↓
Message Queue
    ↓
Telegram Bot API
    ↓
Your Telegram Chat
```

## Configuration

### YAML Configuration (Primary)
File: `config/finance.yaml`
```yaml
notifications:
  telegram:
    bot_token: "YOUR_TOKEN"
    chat_id: "YOUR_CHAT_ID"
    message_thread_id: null  # Optional
    enabled: true
    notifications:
      on_trade_executed: true
      on_trade_closed: true
      on_daily_summary: true
      on_error_alert: true
      on_position_update: false
```

### Environment Fallback
```bash
export TELEGRAM_BOT_TOKEN="YOUR_TOKEN"
export TELEGRAM_CHAT_ID="YOUR_CHAT_ID"
```

## Event Types

1. **TRADE_EXECUTED** - When trade is placed
2. **TRADE_CLOSED** - When position closes
3. **SYSTEM_ERROR** - When critical error occurs
4. **DAILY_SUMMARY** - End of day report

## Message Format

All messages use HTML formatting:
- `<b>Bold</b>` - Bold text
- `<i>Italic</i>` - Italic text
- `<code>Mono</code>` - Monospace
- Emoji support: 📈 📉 ✅ ❌ ⚠️ 💰

## Custom Notifications

```python
from finance_service.notifications.telegram_service import get_or_create_notification_service

async def send_alert():
    service = await get_or_create_notification_service()
    if service:
        await service.send_notification("Your message here")
```

## Files

- `finance_service/notifications/telegram_service.py` - Service implementation
- `finance_service/agents/telegram_agent.py` - Event handler
- `config/finance.yaml` - Configuration

## Debugging

```bash
# Check config
cat config/finance.yaml | grep -A 15 "notifications:"

# View logs
tail -f logs/finance_service.log | grep -i telegram

# Test service
python3 test_telegram_config.py
```

## Status

✅ Ready to use - Complete the 3-step setup for notifications.
