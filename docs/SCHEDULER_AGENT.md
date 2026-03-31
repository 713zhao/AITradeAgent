# SchedulerAgent - Specification & Design

**Agent ID:** `scheduler_agent`  
**File:** `finance_service/agents/scheduler_agent.py`  
**Status:** ✅ Production-ready, actively used  
**Version:** 2.0  
**Last Updated:** 2026-03-30

---

## Overview

SchedulerAgent triggers periodic events at configured intervals. It runs as a background task started at service boot and publishes scheduled **events** to the EventBus. It is the **timekeeper** of the system, driving the 3-tier monitoring architecture.

**Key Responsibility:** Automate periodic tasks across three tiers of monitoring.

---

## Design Philosophy

```
                    ┌─────────────────────────────────┐
                    │  SchedulerAgent.run()            │
                    │  - Start asyncio tasks          │
                    │    with fixed intervals         │
                    └──────────────┬──────────────────┘
                                   │
                    ┌──────────────▼─────────────────┐
                    │  Periodic Event Publishing     │
                    │                                │
                    │  Tier 1: MARKET_SCAN_TRIGGER   │
                    │    (daily — discovery scan)    │
                    │                                │
                    │  Tier 2: PRICE_MONITOR_TRIGGER │
                    │    (every 15 min)              │
                    │                                │
                    │  Tier 3: EXIT_CHECK_TRIGGER    │
                    │    (every 5 min)               │
                    │                                │
                    │  DATA_REFRESH_TRIGGER          │
                    │    (every 30 min)              │
                    │                                │
                    │  SCHEDULE (health check)       │
                    │    (every 4 h)                 │
                    │                                │
                    │  DAILY_REPORT_TRIGGER          │
                    │    (once per day)              │
                    └─────────────────────────────────┘
```

---

## Initialization & Startup

In `app.py` startup:
```python
scheduler_agent = SchedulerAgent(config={})
asyncio.create_task(scheduler_agent.run())
```

The `run()` method schedules tasks and then returns an `AgentReport` indicating success; the actual scheduling loops run as background `asyncio.Task`s.

---

## Scheduled Tasks

| Task Name | Interval | Event Published | Tier | Description |
|-----------|----------|-----------------|------|-------------|
| `discovery_scan` | Daily (24h) | `MARKET_SCAN_TRIGGER` | Tier 1 | Full universe scan → rank → build watchlist |
| `price_monitor` | Every 15 min | `PRICE_MONITOR_TRIGGER` | Tier 2 | Lightweight price refresh for watchlist + held |
| `exit_check` | Every 5 min | `EXIT_CHECK_TRIGGER` | Tier 3 | ExitAgent position monitoring (reactive + strategic) |
| `data_refresh` | Every 30 min | `DATA_REFRESH_TRIGGER` | — | Placeholder for periodic data warming |
| `health_check` | Every 4 hours | `SCHEDULE` | — | Triggers `HealthAgent.perform_health_check()` |
| `daily_report` | Once per day | `DAILY_REPORT_TRIGGER` | — | Daily summary after market close |

---

## Trigger Methods

| Method | Event | Data |
|--------|-------|------|
| `_trigger_discovery_scan()` | `MARKET_SCAN_TRIGGER` | `{"interval": "daily", "mode": "discovery"}` |
| `_trigger_price_monitor()` | `PRICE_MONITOR_TRIGGER` | `{"interval": "15min", "mode": "price_monitor"}` |
| `_trigger_exit_check()` | `EXIT_CHECK_TRIGGER` | `{"interval": "5min"}` |
| `_trigger_hourly_data_refresh()` | `DATA_REFRESH_TRIGGER` | `{}` |
| `_trigger_health_check()` | `SCHEDULE` | `{}` |
| `_trigger_daily_report()` | `DAILY_REPORT_TRIGGER` | `{}` |

---

## 3-Tier Coordination

```
Daily (Tier 1):    ──────────────────────────▶  Discovery Scan
Every 15 min (Tier 2): ─●──●──●──●──●──●──●──●──▶  Price Monitor
Every 5 min (Tier 3):  ●●●●●●●●●●●●●●●●●●●●●●●●●▶  Exit Check
```

- **Tier 1** runs once daily, building the watchlist from the full 100-symbol universe
- **Tier 2** refreshes prices every 15 min for the watchlist + held positions (lightweight)
- **Tier 3** checks held positions only for stop-loss and strategic exit every 5 min

---

## Implementation Details

### `_schedule_task(task_name, coro, interval)`

- Wraps the coroutine in an infinite loop.
- Catches exceptions and logs them.
- Sleeps `interval.total_seconds()` between runs.
- Stores the `asyncio.Task` in `self.scheduled_tasks`.
- On restart, any existing task for that name is cancelled before creating a new one.

---

## Stopping

`await scheduler_agent.stop()` cancels all background tasks and waits for them to finish. Called on service shutdown.

---

## Event Flow Integration

```
Scheduler (daily)        → MARKET_SCAN_TRIGGER   → Orchestrator → MarketScannerAgent.run()
Scheduler (every 15 min) → PRICE_MONITOR_TRIGGER → Orchestrator → scanner.refresh_watchlist_prices()
Scheduler (every 5 min)  → EXIT_CHECK_TRIGGER    → Orchestrator → ExitAgent.run()
```

---

## Error Handling

- Exceptions inside a scheduled task are logged; the loop continues and sleeps before next run.
- If a coroutine raises `CancelledError` (during stop), the task exits cleanly.

---

## Testing

```bash
cd /home/eric/.openclaw/workspace/AITradeAgent
source venv/bin/activate
python -m pytest tests/test_scheduler_agent.py -v
```

---

## Notes

- SchedulerAgent does **not** consider market hours; it publishes triggers regardless. Downstream agents (e.g., `is_market_open()` checks in orchestrator) may skip processing on weekends/after hours.
- Daily report timing uses `timedelta(days=1)`. A real implementation would calculate until next midnight.
- Discovery scan runs immediately on startup, then every 24h thereafter.
- Price monitor runs immediately on startup, then every 15 min thereafter.

---

**Summary:** SchedulerAgent v2.0 drives the 3-tier monitoring architecture: daily discovery (Tier 1), 15-min price refresh (Tier 2), and 5-min exit checks (Tier 3), plus health monitoring and daily reports.
