# TelegramAgent - Specification & Design

**Agent ID:** `telegram_agent`  
**File:** `finance_service/agents/telegram_agent.py`  
**Status:** ✅ Production-ready, actively used (PTB v22.7)  
**Version:** 3.0  
**Last Updated:** 2026-03-29

---

## Overview

TelegramAgent provides a **chat interface** to the trading system. It listens for commands (`/start`, `/status`, `/portfolio`) and sends notifications (trade fills, health alerts, daily summaries, market scans). It uses `python-telegram-bot` v22 (`Application` + polling) and supports optional topic routing via `message_thread_id`.

**Key Responsibility:** bidirectional communication via Telegram Bot API.

---

## Design Philosophy

```
                    ┌─────────────────────────────────┐
                    │  Telegram Bot (long polling)    │
                    │  - User sends /status          │
                    │  - Bot receives update         │
                    └──────────────┬──────────────────┘
                                   │
                    ┌──────────────▼─────────────────┐
                    │  TelegramAgent dispatchers     │
                    │    → _status_command           │
                    │    → _portfolio_command        │
                    └──────────────┬─────────────────┘
                                   │
                    ┌──────────────▼─────────────────┐
                    │  Publish EventBus request      │
                    │  (GET_SYSTEM_STATUS, etc.)     │
                    └──────────────┬─────────────────┘
                                   │
                    ┌──────────────▼─────────────────┐
                    │  Other agents respond          │
                    │  HealthAgent sends messages    │
                    └─────────────────────────────────┘
```

---

## Initialization

From `app.py` startup:
```python
telegram_agent = TelegramAgent(config={})
orchestrator.telegram_agent = telegram_agent
health_agent.telegram_agent = telegram_agent
```

TelegramAgent reads configuration from:
- `.env` variables:
  - `TELEGRAM_BOT_TOKEN` (required)
  - `TELEGRAM_CHAT_ID` (required, numeric chat ID)
  - `TELEGRAM_MESSAGE_THREAD_ID` (optional, for forum topics)

If any required config missing, the agent is **disabled** (`self.enabled=False`).

---

## Command Handlers

| Command | Handler | Description |
|---------|---------|-------------|
| `/start` | `_start_command` | Greets the user |
| `/status` | `_status_command` | Publishes `GET_SYSTEM_STATUS` event; sends "Fetching..." placeholder |
| `/portfolio` | `_portfolio_command` | Publishes `GET_PORTFOLIO_STATE` event; sends placeholder |

Handlers publish events to the EventBus; the orchestrator routes replies back to TelegramAgent for sending.

---

## Sending Messages

### `send_message(chat_id: str, message: str, parse_mode: Optional[str] = None)`

- Uses `self.bot.send_message(...)`
- If `self.thread_id` is set (from `TELEGRAM_MESSAGE_THREAD_ID`), includes `message_thread_id` parameter.
- Logs success or error.

### `send_scheduled_report(report_data: Dict, chat_id: Optional[str]=None)`

Used by orchestrator for scheduled summaries (daily report). Formats as Markdown.

---

## Event Flow Integration

```
Telegram command → handler → EventBus
    ↓
Orchestrator (or HealthAgent, etc.) produces reply
    ↓
TelegramAgent.send_message(chat_id, text)
```

For asynchronous replies, orchestrator can store `chat_id` in the event and later call `telegram_agent.send_message`.

---

## Configuration (.env)

```
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
TELEGRAM_CHAT_ID=8383381149
TELEGRAM_MESSAGE_THREAD_ID=251  # optional; for topic-based chats
```

No YAML config section; all via environment variables.

---

## PTB Version Compatibility

- **v22.7** (current): Uses `Application.builder().token(...).build()` and `CommandHandler`.
- Earlier code used `Updater(use_context=True)` (PTB v13); that was incompatible with Python 3.13 and PTB v22. All references to `use_context` removed.

---

## Error Handling

- Sending errors are logged (`logger.error`) but do not raise.
- If bot token invalid at startup, agent is disabled and logs warning.

---

## Testing

Test suite: `tests/test_telegram_agent.py` covers:
- Initialization with/without token/chat_id
- Command handlers publish correct events
- `send_message` includes `message_thread_id` when set

Run:
```bash
cd /home/eric/.openclaw/workspace/AITradeAgent
source venv/bin/activate
python -m pytest tests/test_telegram_agent.py -v
```

---

## Notes

- TelegramAgent **does not** store chat state between updates; it is stateless.
- Long polling runs as a background task started in `app.py`:
  ```python
  asyncio.create_task(_orchestrator.telegram_agent.run())
  ```
- Stop the service gracefully to close the polling loop.
- For group/channel topics, ensure the bot is an admin with permission to post in the topic.

---

## Recent Fixes (2026-03-31)

| Fix | Description |
|-----|-------------|
| Config override bug | Orchestrator was passing empty strings for `telegram_bot_token` and `telegram_chat_id` from YAML config to TelegramAgent, overriding valid values from `.env`. Fixed: only include these keys in the simple_config if YAML provides non-empty values. TelegramAgent now correctly falls back to `.env` settings. |
| Routing parameter | Message sending now uses `target` parameter for Telegram channel instead of `chatId` to ensure delivery to the correct chat (8383381149). |

---

**Summary:** TelegramAgent is the user-facing interface. It centralizes all outbound notifications and provides simple text commands. It is fully asynchronous and integrates cleanly with the EventBus.
