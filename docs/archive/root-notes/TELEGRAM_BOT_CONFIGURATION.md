# 🤖 Telegram Bot Configuration - Complete Setup Guide

Your AITradeAgent Telegram bot has been configured! Follow these steps to get trading notifications.

## ✅ What's Been Done

1. **Bot Token Configured** ✅
   - Token: `8694519756:AAGxp6d7Fho3-696h4ae4tHvjcVmtazQUOw`
   - Location: `config/finance.yaml`

2. **Configuration in YAML** ✅
   - File: `config/finance.yaml`
   - Section: `notifications.telegram`
   - Enabled: `true`

3. **Scripts Created** ✅
   - `setup_telegram.py` - Get your Chat ID
   - `test_telegram_config.py` - Verify configuration
   - `finance_service/notifications/telegram_service.py` - Notification engine

4. **Documentation** ✅
   - `TELEGRAM_QUICK_START.md` - Quick reference
   - `TELEGRAM_SETUP_GUIDE.md` - Detailed guide
   - `TELEGRAM_INTEGRATION.md` - Technical details

## 📋 Next Steps (3 Simple Steps)

### Step 1: Get Your Chat ID (2 minutes)

```bash
cd /home/claw.zhao/.openclaw/workspace/AITradeAgent
source .venv/bin/activate
python3 setup_telegram.py
```

Then in Telegram:
- Find your bot
- Send ANY message (Hi, Hello, etc.)
- The bot will respond with your **Chat ID**
- Copy the Chat ID value

Press `Ctrl+C` to stop the script.

### Step 2: Update Configuration (1 minute)

Edit: `config/finance.yaml`

Find this section:
```yaml
notifications:
  telegram:
    bot_token: "8694519756:AAGxp6d7Fho3-696h4ae4tHvjcVmtazQUOw"
    chat_id: ""  # ← Fill this with your Chat ID
```

Replace empty `chat_id` with your Chat ID (just numbers, like `123456789`):
```yaml
    chat_id: "123456789"
```

### Step 3: Test & Restart (1 minute)

Test configuration:
```bash
python3 test_telegram_config.py
```

Restart the service:
```bash
# Stop current
pkill -f "run_finance_service.py"

# Start new
python3 run_finance_service.py
```

## ✨ You're All Set!

Once restarted, you'll receive:
- 📈 **Trade Execution Alerts** - When orders are placed
- 📉 **Position Closed Updates** - When positions close with P&L
- ⚠️ **Error Alerts** - When critical issues occur  
- 📊 **Daily Summaries** - Daily trading statistics

All sent directly to your Telegram!

## 🎯 Notification Examples

### Trade Executed
```
📈 TRADE EXECUTED

Symbol: AAPL
Action: BUY
Quantity: 10
Entry Price: $150.00
Target Price: $160.00
Stop Loss: $145.00
Confidence: 95%

💰 Potential Profit: $100.00 (+6.67%)
```

### Position Closed
```
✅ POSITION CLOSED - PROFIT

Symbol: AAPL
Direction: BUY
Entry Price: $150.00
Exit Price: $158.50
Quantity: 10

💵 P&L: +$85.00 (+5.67%)
```

## ❓ Quick Troubleshooting

| Issue | Solution |
|-------|----------|
| Bot doesn't respond to setup | Retry setup_telegram.py (rate limits) |
| Can't find bot in Telegram | Check bot token is correct |
| Messages not appearing | Verify Chat ID in config/finance.yaml |
| Format looks wrong | HTML formatting - check message content |

## 📁 Files Created/Modified

| File | Status | Purpose |
|------|--------|---------|
| `config/finance.yaml` | ✅ Modified | Added Telegram config section |
| `setup_telegram.py` | ✅ Created | Get Chat ID interactively |
| `test_telegram_config.py` | ✅ Created | Verify configuration |
| `finance_service/notifications/telegram_service.py` | ✅ Created | Notification engine |
| `finance_service/notifications/__init__.py` | ✅ Created | Package initialization |

## 🚀 Quick Reference Commands

```bash
# Get Chat ID
python3 setup_telegram.py

# Test configuration
python3 test_telegram_config.py

# View Telegram logs
tail -f logs/finance_service.log | grep -i telegram

# Restart service
pkill -f "run_finance_service.py"
python3 run_finance_service.py

# Check configuration
cat config/finance.yaml | grep -A 15 "notifications:"
```

## 📚 More Information

- **Setup Guide:** See `TELEGRAM_SETUP_GUIDE.md`
- **Quick Start:** See `TELEGRAM_QUICK_START.md`
- **Technical Details:** See `TELEGRAM_INTEGRATION.md`

## ✅ Checklist

- [ ] Run `setup_telegram.py` and get Chat ID
- [ ] Update `chat_id` in `config/finance.yaml`
- [ ] Run `test_telegram_config.py` to verify
- [ ] Restart `run_finance_service.py`
- [ ] Execute a test trade to verify notifications
- [ ] Enjoy automated trading alerts! 🎉

---

**Your Telegram bot is ready to use!** 🚀

Once you complete these 3 simple steps, all your trades will be notified to Telegram automatically.
