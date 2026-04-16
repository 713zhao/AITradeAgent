# AITradeAgent - Broker & Execution Configuration Summary

## 🎯 Current Status

| Setting | Value | Status |
|---------|-------|--------|
| **Broker** | `paper` | ✅ Active (Default) |
| **Mode** | Paper Trading | 🟢 Testing Mode (Safe) |
| **Initial Cash** | $100,000 | ✅ Configured |
| **Slippage** | 1 basis point | ✅ Realistic |
| **Auto Execute** | Enabled | ✅ Configured |
| **Approval Gate** | Not Required | ✅ Configured |

---

## 📁 Configuration Files

### 1. **Main Configuration**
```
Location: config/finance.yaml
Section: execution
Status: ✅ Configured for Paper Trading
```

**Current Configuration**:
```yaml
execution:
  broker: paper
  broker_config:
    paper:
      initial_cash: 100000.0
      slippage_bps: 1.0
      fill_delay_seconds: 1.0
      simulate_partial_fills: false
```

### 2. **Environment Variables**
```
Location: .env (in project root)
Purpose: Store sensitive credentials
```

**For Tiger Brokers (when enabled)**:
```bash
TIGER_ACCOUNT_ID=your_account_id
TIGER_PRIVATE_KEY_PATH=/path/to/private/key
TIGER_SERVER=https://api.tigerbrokers.com
```

---

## 🚀 Quick Start

### Option 1: Paper Trading (Recommended - Currently Active)
```bash
# ✅ Already configured and ready to use!
# Just start the service:
cd /home/claw.zhao/.openclaw/workspace/AITradeAgent
python3 run_finance_service.py

# Monitor logs:
tail -f finance_service_restart.log | grep -E "ExecutionAgent|Trade"
```

### Option 2: Real Trading (Tiger Brokers)
```bash
# Step 1: Stop the service
pkill -f "run_finance_service.py"

# Step 2: Use the quick switch script
cd /home/claw.zhao/.openclaw/workspace/AITradeAgent
bash BROKER_QUICK_SWITCH.sh

# Select option 2 for Tiger Brokers and provide credentials

# Step 3: Restart service
python3 run_finance_service.py &
```

---

## 📊 Feature Breakdown

### Paper Trading Features (Current)
- ✅ Simulated order fills
- ✅ Realistic slippage simulation
- ✅ Position tracking
- ✅ Cash management
- ✅ Order status tracking
- ✅ No real money at risk
- ✅ Instant feedback

### When Switching to Real Trading (Tiger Brokers)
- ✅ Real order execution
- ✅ Live market data
- ✅ Global market access
- ✅ Real money transfers
- ⚠️ Real profit/loss risk

---

## 🔄 Broker Architecture

```
Application
    ↓
ExecutionAgent ← Fixed Earlier ✅
    ↓
BrokerFactory ← Creates correct broker type
    ↓
┌─────────────────────────────┐
│ Paper Broker (Current)      │  Safe testing, instant fills
│ Tiger Brokers (Available)   │  Real trading, real money
│ Alpaca (Planned)            │  Future integration
└─────────────────────────────┘
```

---

## ✅ Validation Checklist

### Paper Trading (Current Setup)
- [x] Broker configured in YAML
- [x] ExecutionAgent fixed to use broker
- [x] BrokerFactory creates PaperBroker
- [x] Initial cash set to $100,000
- [x] Ready to execute trades
- [x] No credentials needed

### For Real Trading with Tiger Brokers
- [ ] Tiger Brokers account created
- [ ] Account ID obtained
- [ ] Private key downloaded
- [ ] `.env` file configured with credentials
- [ ] `tigeropen` SDK installed
- [ ] `config/finance.yaml` updated (broker: tiger)
- [ ] Connection tested
- [ ] Small initial trades tested

---

## 🎓 How to Use

### Manual Switching via Script
```bash
cd /home/claw.zhao/.openclaw/workspace/AITradeAgent
bash BROKER_QUICK_SWITCH.sh

# Menu options:
# 1. Switch to Paper Trading
# 2. Switch to Tiger Brokers  
# 3. Show Broker Configuration
# 4. Test Broker Connection
```

### Manual Switching via YAML Edit
```bash
# Edit config/finance.yaml
# Change line: broker: paper
# To:         broker: tiger

# Then restart service
```

---

## 🔐 Security Notes

### Paper Trading
- No credentials needed
- Safe for development
- All transactions are simulated

### Real Trading (Tiger Brokers)
- **KEEP CREDENTIALS SECURE**
- Never commit `.env` to git
- Use strong private keys
- Monitor account regularly
- Start with small amounts
- Keep stop-loss configured

---

## 📈 Expected Trading Flow

```
1. SchedulerAgent triggers scan every 15 min
2. MarketScannerAgent finds opportunities
3. AnalysisAgent calculates indicators
4. StrategyAgent generates proposals
5. RiskAgent validates trades
6. ExecutionAgent calls broker.place_order()
   ├─ Paper Broker → Simulated instant fill
   └─ Tiger Broker → Real execution
7. PortfolioAgent updates positions
8. TelegramAgent sends notifications
```

---

## 🆘 Troubleshooting

### "No trades executing?"
1. Check ExecutionAgent is working: `grep ExecutionAgent finance_service_restart.log`
2. Verify broker is connected: `grep "Broker connected" finance_service_restart.log`
3. Check strategy is finding signals: `grep "TRADE_PROPOSAL" finance_service_restart.log`

### "Error creating broker"
- Verify config/finance.yaml syntax is correct
- Check broker name is lowercase: `paper` not `Paper`
- Ensure all indentation is correct in YAML

### "Tiger Broker credentials error"
- Check `.env` file exists
- Verify `TIGER_ACCOUNT_ID` is set
- Verify `TIGER_PRIVATE_KEY_PATH` points to valid file
- Test connection: `bash BROKER_QUICK_SWITCH.sh` → option 4

---

## 📚 Related Documentation

- **[BROKER_SETUP_GUIDE.md](BROKER_SETUP_GUIDE.md)** - Detailed setup instructions
- **[TELEGRAM_QUICK_START.md](TELEGRAM_QUICK_START.md)** - Telegram notifications
- **[config/finance.yaml](config/finance.yaml)** - Full configuration file

---

## 🚀 Next Steps

1. **Test Paper Trading** (Current - Safe)
   ```bash
   python3 run_finance_service.py &
   ```

2. **Monitor Trades**
   ```bash
   tail -f finance_service_restart.log | grep -E "ExecutionAgent|Trade"
   ```

3. **When Ready, Switch to Real Trading**
   ```bash
   bash BROKER_QUICK_SWITCH.sh  # Option 2
   ```

---

**Last Updated**: April 16, 2026  
**Status**: ✅ Fully Configured and Ready to Use
