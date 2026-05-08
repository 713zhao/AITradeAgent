# Telegram Message Types Reference

Quick guide showing which Telegram messages include LLM analysis and which don't.

---

## 📱 All Message Types

### ✅ Messages WITH LLM Analysis

#### **Trade About to Execute** 
- **When**: Before a trade executes (signal detected)
- **Trigger**: `send_pre_execution_notification()` in app.py
- **LLM Content**:
  - 📍 Market Environment (Risk-On/Off, Volatility, VIX)
  - ⚠️ Anomaly Warnings (RSI extremes, volume spikes, MACD divergence)
  - 💡 Strategy Suggestions (LLM-powered recommendations)
- **Example Title**: "⚡ Trade About to Execute"
- **Frequency**: Per trade signal
- **Format**: Markdown with emojis

```
⚡ Trade About to Execute
Symbol: AAPL
...
📍 Market Context: 🟢 Risk-On | 📉 Vol: Low | VIX: 18.5
⚠️ Alert: RSI > 85 (overbought condition)
💡 Suggestion: Strong technicals... Consider smaller size...
```

---

### ❌ Messages WITHOUT LLM Analysis

#### **Hourly Portfolio Report**
- **When**: Every hour (on schedule)
- **What**: Portfolio equity, P&L, positions, performance
- **LLM Content**: ❌ NONE
- **Frequency**: Hourly
- **Example**: Equity: $50,000 | Return: +2.5% | Drawdown: -1.2%

#### **Daily Summary**
- **When**: Once per day (on schedule)
- **What**: Trade history summary, company names, P&L
- **LLM Content**: ❌ NONE
- **Frequency**: Daily
- **Example**: 3 trades today | 2 wins | Total P&L: +$500

#### **Trade Executed**
- **When**: When a trade fills/executes
- **What**: Filled price, quantity, P&L, hold duration
- **LLM Content**: ❌ NONE
- **Trigger**: `Events.TRADE_EXECUTED`
- **Frequency**: Per filled trade
- **Example**: AAPL BUY 10 @ $150.25 | P&L: +$125

#### **Error Alert**
- **When**: System errors occur (data fetch failures)
- **What**: Error type, details, symbols affected
- **LLM Content**: ❌ NONE
- **Trigger**: Exception handling in data pipeline
- **Frequency**: Only on errors
- **Example**: Data Fetch Failures: [APPL, GOOG, TSLA]

#### **Telegram Bot Commands**
- **When**: User sends command
- **Commands**: `/start`, `/status`, `/portfolio`
- **LLM Content**: ❌ NONE
- **Frequency**: On request
- **Example Response**: "Bot is running. Type /portfolio for current holdings."

---

## Message Flow Diagram

```
MARKET SCAN TRIGGERED
├─ No signals found
│  └─ (No notifications)
│
├─ Signal detected (trade setup found)
│  └─ ⚡ "Trade About to Execute" [WITH LLM] ← NEW!
│     ├─ Market regime context ← NEW
│     ├─ Anomaly warnings ← NEW
│     └─ LLM suggestion ← NEW
│
└─ Trade execution started
   ├─ Trade filled
   │  └─ "Trade Executed" [WITHOUT LLM]
   │
   └─ Errors during scan
      └─ Error Alert [WITHOUT LLM]

HOURLY TRIGGER
└─ "Hourly Portfolio Report" [WITHOUT LLM]

DAILY TRIGGER
└─ "Daily Summary" [WITHOUT LLM]
```

---

## Comparison Table

| Aspect | Trade About to Execute | Portfolio Reports | Trade Executed | Other |
|--------|---|---|---|---|
| **Message Type** | ⚡ Pre-execution | 📊 Portfolio review | ✅ Confirmation | 🔔 Alerts/Commands |
| **When** | Before trade | Hourly | After fill | Various |
| **Market Regime** | ✅ YES | ❌ NO | ❌ NO | ❌ NO |
| **Anomaly Warnings** | ✅ YES | ❌ NO | ❌ NO | ❌ NO |
| **LLM Suggestion** | ✅ YES | ❌ NO | ❌ NO | ❌ NO |
| **Trade Details** | ✅ Entry/Stop | ❌ NO | ✅ Fill price | ✅ If relevant |
| **P&L Info** | Signal confidence | Equity, Return % | Realized P&L | N/A |
| **Portfolio Context** | Equity, Cash | Full details | Brief context | N/A |

---

## What to Expect

### When Trading

**You WILL see LLM features in:**
- ✅ Every "Trade About to Execute" notification
  - Market context
  - Any detected anomalies
  - AI suggestion

**You will NOT see LLM in:**
- ❌ Trade execution confirmations (when filled)
- ❌ Hourly portfolio reports
- ❌ Daily trade summaries
- ❌ Error messages
- ❌ Bot command responses

### Why This Design

**Pre-execution (WITH LLM):**
- LLM helps with trade decision-making
- Real-time market context is valuable
- Anomaly warnings prevent bad entries
- Suggestions aid trade sizing

**Post-execution (WITHOUT LLM):**
- Trade already executed, decision made
- Focus on execution details (fill, P&L)
- Historical analysis, not decision support

**Portfolio monitoring (WITHOUT LLM):**
- Standard metrics (equity, return %)
- Trend monitoring, not AI analysis
- Simple, frequent updates

---

## Configuration

### To Enable/Disable LLM in Pre-Execution

LLM features are automatic but can be disabled:

In `finance_service/app.py` (lines ~550-575):
```python
# To disable market regime display:
_market_regime = None

# To disable anomaly warnings:
_anomaly_explanation = None

# To disable LLM suggestions:
_trade_suggestion = None
```

### Thresholds

Anomaly detection thresholds in `telegram_llm_enhancement.py`:
```python
# Line 50: RSI overbought (default: 85)
if rsi > 85:

# Line 53: RSI oversold (default: 15)  
elif rsi < 15:

# Line 63: Volume spike (default: 2.5x)
if volume_ratio > 2.5:
```

---

## FAQ

**Q: Can I see LLM analysis in hourly reports?**  
A: No. LLM features are pre-execution only. Hourly reports show portfolio metrics (equity, P&L, positions).

**Q: Why no LLM in trade execution confirmations?**  
A: Trade already executed. Post-execution analysis would be useful for review but isn't implemented yet.

**Q: How often will I see "Trade About to Execute" with LLM?**  
A: Whenever a trading signal is detected (frequency depends on market activity and strategy).

**Q: Can anomalies prevent a trade?**  
A: No. Anomalies are warnings only. They appear in the notification but don't block execution.

**Q: What if LLM is unavailable?**  
A: Trade notification still sends immediately with all other data. It just won't have the 💡 Suggestion.

**Q: How long does LLM analysis add to notification time?**  
A: ~2-3 seconds, but it runs in parallel so doesn't delay the trade execution.

---

**Last Updated**: May 8, 2026  
**Status**: ✅ Complete
