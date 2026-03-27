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
- Execute a `git rm` command for the tracked `.py` files, and `rm` for untracked logs/outs.
- The script must list the explicitly deleted files for transparency.

## 2. Telegram Topic Support
### Configuration Updates
- **Environment Variable**: Introduce `TELEGRAM_MESSAGE_THREAD_ID`.
- **Pydantic Config (`finance_service/core/pydantic_config.py`)**:
  - Add `TELEGRAM_MESSAGE_THREAD_ID: Optional[int] = Field(None, description="Telegram message thread ID for topics")`.
  - Add a `@field_validator("TELEGRAM_MESSAGE_THREAD_ID", mode="before")` to handle empty strings `""` by converting them to `None`.
- **Core Config (`finance_service/core/config.py`)**:
  - Expose `TELEGRAM_MESSAGE_THREAD_ID = _pydantic_settings.TELEGRAM_MESSAGE_THREAD_ID`.

### Agent Updates (`finance_service/agents/telegram_agent.py`)
- **Initialization**:
  - Load `raw_thread_id = config.get("telegram_message_thread_id", Config.TELEGRAM_MESSAGE_THREAD_ID)`.
  - Set `self.thread_id = int(str(raw_thread_id).strip()) if raw_thread_id and str(raw_thread_id).strip() else None`.
- **Message Sending (`send_message`, `send_scheduled_report`)**:
  - Modify the `self.bot_instance.send_message` calls to conditionally include `message_thread_id=self.thread_id` if `self.thread_id is not None`.

### Approval Gate Updates (`finance_service/tools/approval_gate.py`)
- **Initialization (`TelegramApprovalGate`)**:
  - Load `raw_thread_id = Config.TELEGRAM_MESSAGE_THREAD_ID`.
  - Set `self.thread_id = int(str(raw_thread_id).strip()) if raw_thread_id and str(raw_thread_id).strip() else None`.
- **Message Sending (`send_approval_request`)**:
  - Modify the `self.bot_instance.send_message` call to conditionally include `message_thread_id=self.thread_id` if `self.thread_id is not None`.

## Execution Plan
1. Delete matching temporary files from the root directory.
2. Update configuration files to support the thread ID.
3. Apply changes to Telegram agents and approval gates.
4. Run standard tests (if any) to ensure no regressions.