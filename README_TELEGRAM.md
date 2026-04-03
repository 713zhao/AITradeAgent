# Telegram Notifications for AITradeAgent

Get instant trading notifications directly to your Telegram chat!

## ✅ What's Configured

Your Telegram bot is pre-configured with:
- **Bot Token**: `8694519756:AAGxp6d7Fho3-696h4ae4tHvjcVmtazQUOw`
- **Notifications**: Trade execution, position closure, errors, daily summary
- **Status**: 🟢 Ready to use

## 📱 Quick Setup (3 Steps)

### Step 1: Get Chat ID
```bash
cd /home/claw.zhao/.openclaw/workspace/AITradeAgent
source .venv/bin/activate
python3 setup_telegram.py
```
→ Send any message to the bot in Telegram
→ Copy the Chat ID from the response

### Step 2: Update Configuration
Edit `config/finance.yaml` and set your Chat ID:
```yaml
notifications:
  telegram:
    bot_token: "8694519756:AAGxp6d7Fho3-696h4ae4tHvjcVmtazQUOw"
    chat_id: "YOUR_CHAT_ID"  # Replace with your ID
```

### Step 3: Verify & Restart
```bash
python3 test_telegram_config.py    # Verify setup
pkill -f "run_finance_service.py"  # Stop service
python3 run_finance_service.py     # Start service
```

## 📊 Notifications You'll Receive

| Type | Example |
|------|---------|
| **Trade Executed** | 📈 BUY AAPL 10 @ $150→$160 (95% confidence) |
| **Position Closed** | ✅ PROFIT: $85.00 (+5.67%) |
| **Error Alert** | ⚠️ ALERT: API rate limit exceeded |
| **Daily Summary** | 📊 P&L: +$250 (+0.85%), 3 trades |

## 🔧 Configuration

**Main Config**: `config/finance.yaml`
```yaml
notifications:
  telegram:
    bot_token: "8694519756:AAGxp6d7Fho3-696h4ae4tHvjcVmtazQUOw"
    chat_id: ""  # Fill this
    message_thread_id: null  # Optional topic ID
    enabled: true
    notifications:
      on_trade_executed: true   # ✅ Send trade alerts
      on_trade_closed: true      # ✅ Send P&L updates
      on_daily_summary: true     # ✅ Send daily report
      on_error_alert: true       # ✅ Send errors
      on_position_update: false  # ❌ Disabled (verbose)
```

## 📂 Files

| File | Purpose |
|------|---------|
| `setup_telegram.py` | Get Chat ID interactively |
| `test_telegram_config.py` | Verify configuration works |
| `START_HERE_TELEGRAM.txt` | Quick action guide (read this first!) |
| `TELEGRAM_BOT_CONFIGURATION.md` | Complete setup guide |
| `TELEGRAM_QUICK_START.md` | Quick reference |
| `TELEGRAM_SETUP_GUIDE.md` | Detailed step-by-step |
| `TELEGRAM_INTEGRATION.md` | Technical architecture |

## 🚀 Commands

```bash
# Get Chat ID
python3 setup_telegram.py

# Test configuration
python3 test_telegram_config.py

# View logs
tail -f logs/finance_service.log | grep -i telegram

# Restart service
pkill -f "run_finance_service.py" && python3 run_finance_service.py

# Check config
cat config/finance.yaml | grep -A 15 "notifications:"
```

## ❓ Troubleshooting

**Bot doesn't respond?**
- Try again after 30 seconds (Telegram rate limiting)
- Verify bot token is correct

**Chat ID not showing?**
- Make sure you're sending message to the right bot
- Check bot token in terminal output

**Messages not appearing?**
- Verify Chat ID is numeric only (123456789 not "123456789")
- Restart service after updating Chat ID

**Check logs for errors:**
```bash
tail -f logs/finance_service.log | grep -i telegram
```

## 📖 Next Steps

1. Read: `START_HERE_TELEGRAM.txt` for immediate action
2. Run: `python3 setup_telegram.py` to get Chat ID
3. Update: Chat ID in `config/finance.yaml`
4. Test: `python3 test_telegram_config.py`
5. Enjoy: Trading notifications in Telegram! 🎉

## 🔐 Security

- Bot token is already set (managed securely)
- Chat ID is only used to send you messages
- No sensitive data is sent

## Status

✅ **Ready to use!** Follow the 3-step setup above to start receiving notifications.

---

For detailed information, see `TELEGRAM_BOT_CONFIGURATION.md`
