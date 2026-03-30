# HealthAgent - Specification & Design

**Agent ID:** `health_agent`  
**File:** `finance_service/agents/health_agent.py`  
**Status:** ✅ Production-ready, actively used  
**Version:** 2.0  
**Last Updated:** 2026-03-29

---

## Overview

HealthAgent monitors **system health** and **portfolio performance**, raising alerts via Telegram when thresholds are breached. It sends trade notifications immediately after executions and provides a daily summary after market close. It also responds to `GET_SYSTEM_STATUS` queries from Telegram commands.

**Key Responsibility:** Proactive monitoring and notification.

---

## Design Philosophy

```
                    ┌─────────────────────────────────┐
                    │  Events: TRADE_EXECUTED,        │
                    │  SCHEDULE (periodic health),   │
                    │  GET_SYSTEM_STATUS,            │
                    │  DAILY_REPORT_TRIGGER          │
                    └──────────────┬──────────────────┘
                                   │
                    ┌──────────────▼─────────────────┐
                    │  HealthAgent.run(event_type,   │
                    │               payload)         │
                    │  - Check drawdown, portfolio   │
                    │  - Build alert messages        │
                    └──────────────┬─────────────────┘
                                   │
                    ┌──────────────▼─────────────────┐
                    │  TelegramAgent.send_message    │
                    │  (or log if no Telegram)       │
                    └─────────────────────────────────┘
```

---

## Input Parameters & Events

### `run(event_type: str, payload: Optional[Dict] = None) -> AgentReport`

Handles multiple event types:

| event_type | Action | Payload Keys |
|------------|--------|--------------|
| `SCHEDULE` | Periodic health check (`perform_health_check`) | – |
| `TRADE_EXECUTED` | Send trade notification (`send_trade_notification`) | `execution_result` |
| `DAILY_REPORT_TRIGGER` | Send daily summary after market close (`send_daily_summary`) | – |
| `GET_SYSTEM_STATUS` | Return health status dict (`get_health_status`) | optional `chat_id` |

---

## Outputs

### Health Check (`perform_health_check`)

- Queries `PortfolioAgent` for equity metrics.
- Compares drawdown to thresholds (`drawdown_warning_pct`, `drawdown_critical_pct`).
- Sends Telegram alert if thresholds breached and cooldown elapsed.

**Telegram message example:**
```
🦞 AiTradeAgent Health Alert 🦞
• Drawdown exceeds 10% (current: 12.5%)
• Trading paused until recovered

📊 Current Metrics:
Equity: $98,123.45
Total Return: -1.87%
Drawdown: 12.5%
Positions: 5
Trades: 27
```

### Trade Notification (`send_trade_notification`)

```
🦞 Trade Executed
• Symbol: NVDA
• Action: BUY
• Quantity: 10
• Price: $150.25
• Status: FILLED

Portfolio: $102,954.04, 5 positions
```

### Daily Summary (`send_daily_summary`)

```
📊 Daily Portfolio Summary - 2026-03-28
Equity: $102,954.04
Total Return: +2.95%
Drawdown: 0.00%
Positions: 5
Trades Today: 2

Current Positions:
  NVDA: 10 @ $148.50
  AMD: 5 @ $135.20

Today's Trades:
  BUY NVDA x10 @ $148.50
  SELL AMD x2 @ $138.00
```

---

## Configuration

```yaml
finance:
  health_agent:
    drawdown_warning_pct: 10.0   # warning level
    drawdown_critical_pct: 20.0  # critical (may pause trading)
    check_interval_hours: 4
    alert_cooldown_hours: 4
```

---

## Event Flow Integration

```
TRADE_EXECUTED
    ↓ HealthAgent.send_trade_notification
    → Telegram

SCHEDULE (every 4h)
    ↓ HealthAgent.perform_health_check
    → If drawdown > warning → alert via Telegram

DAILY_REPORT_TRIGGER (after market close)
    ↓ HealthAgent.send_daily_summary
    → Telegram

GET_SYSTEM_STATUS (from Telegram /status)
    ↓ HealthAgent.get_health_status
    → Returns dict with status, metrics, alerts
```

---

## Telegram Integration

HealthAgent **requires** a configured `TelegramAgent` (injected by orchestrator). It uses `self.telegram_agent.chat_id` and `send_message()`. If Telegram is disabled, it logs warnings and skips sending.

---

## Error Handling

- Missing `PortfolioAgent` → returns error status.
- Portfolio query fails → logs error, continues.
- Telegram send fails → logs error but does not raise.

---

## Testing

Test suite: `tests/test_health_agent.py` (exists) covers:
- Health check thresholds
- Alert cooldown logic
- Trade notification formatting
- Daily summary content

Run:
```bash
cd /home/eric/.openclaw/workspace/AITradeAgent
source venv/bin/activate
python -m pytest tests/test_health_agent.py -v
```

---

## Notes

- HealthAgent is **not** the same as orchestrator health. It focuses on portfolio metrics.
- System-level health (service up, event bus) is monitored separately (`/health` endpoint).
- The agent uses `config_engine` for thresholds but also accesses `self.telegram_agent.chat_id` directly (fixed in 2026-03-28 patch).
- Daily summary uses `datetime.date.today()`; timezone awareness may need refinement.

---

**Summary:** HealthAgent provides automated monitoring and notification, keeping you informed of portfolio health, trade outcomes, and daily recaps. It is a critical component for oversight in both paper and live trading.
