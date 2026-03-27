# Telegram Topic Setup and Root Cleanup Design

## Overview
This design covers two primary objectives:
1. **Root Cleanup**: Removing cluttered temporary and test files from the root directory to maintain a clean project structure.
2. **Telegram Topic Support**: Enabling notifications to be routed to a specific Telegram topic/thread (`message_thread_id`) rather than just the general chat, which is required to send messages to `https://t.me/c/3797383744/13/83` (Topic ID: 13).

## 1. Root Cleanup
### Scope
The root directory will be cleaned of the following file patterns:
- `test_*.py`
- `check_*.py`
- `fix_*.py`
- `*.log`
- `*.out`

### Action
- Execute a deletion command targeting these explicit patterns in the root directory.
- This will not affect actual application code, `pytest` files inside the `tests/` directory, or legitimate documentation.

## 2. Telegram Topic Support
### Configuration Updates
- **Environment Variable**: Introduce `TELEGRAM_MESSAGE_THREAD_ID`.
- **Pydantic Config (`finance_service/core/pydantic_config.py`)**:
  - Add `TELEGRAM_MESSAGE_THREAD_ID: str = Field("", description="Telegram message thread ID for topics")`.
- **Core Config (`finance_service/core/config.py`)**:
  - Expose `TELEGRAM_MESSAGE_THREAD_ID = _pydantic_settings.TELEGRAM_MESSAGE_THREAD_ID`.

### Agent Updates (`finance_service/agents/telegram_agent.py`)
- **Initialization**:
  - Load `self.thread_id = config.get("telegram_message_thread_id", Config.TELEGRAM_MESSAGE_THREAD_ID)`.
- **Message Sending (`send_message`, `send_scheduled_report`)**:
  - Modify the `self.bot_instance.send_message` calls to include `message_thread_id=self.thread_id` if `self.thread_id` is truthy.
  - Wait, Telegram API requires `message_thread_id` to be an integer if provided, or cast it appropriately.

### Approval Gate Updates (`finance_service/tools/approval_gate.py`)
- **Initialization (`TelegramApprovalGate`)**:
  - Load `self.thread_id = Config.TELEGRAM_MESSAGE_THREAD_ID`.
- **Message Sending (`send_approval_request`)**:
  - Modify the `self.bot_instance.send_message` call to include `message_thread_id=self.thread_id` if `self.thread_id` is truthy.

## Execution Plan
1. Delete matching temporary files from the root directory.
2. Update configuration files to support the thread ID.
3. Apply changes to Telegram agents and approval gates.
4. Run standard tests (if any) to ensure no regressions.