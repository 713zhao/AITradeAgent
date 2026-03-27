# Telegram Topic Setup and Root Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clean up the root directory by removing temporary files and add support for sending Telegram messages to specific topics/threads.

**Architecture:** Deletes temporary files directly using shell commands. Updates Pydantic configuration to support an optional integer for the Telegram thread ID, and modifies the `python-telegram-bot` API calls in the agent and approval gates to conditionally pass this parameter.

**Tech Stack:** `python`, `pydantic v2`, `python-telegram-bot`, `bash`

---

### Task 1: Root Directory Cleanup

**Files:**
- Modify: `root directory`

- [ ] **Step 1: Delete temporary untracked log and out files**

```bash
ls -1 *.log *.out 2>/dev/null || true
rm -vf *.log *.out || true
```

- [ ] **Step 2: Remove tracked temporary python scripts**

```bash
ls -1 check_*.py fix_*.py test_*.py 2>/dev/null || true
git rm -q --ignore-unmatch check_*.py fix_*.py test_*.py || true
```

- [ ] **Step 3: Commit the cleanup**

```bash
git diff --cached --exit-code >/dev/null || git commit -m "chore: Remove temporary logs and scripts from root directory"
```

### Task 2: Configuration Updates

**Files:**
- Modify: `finance_service/core/pydantic_config.py`
- Modify: `finance_service/core/config.py`

- [ ] **Step 1: Add field to Pydantic config**

In `finance_service/core/pydantic_config.py`, ensure imports:
```python
from typing import Dict, Any, Optional, List
from pydantic import Field, field_validator
```

Add `TELEGRAM_MESSAGE_THREAD_ID` under "Approval configuration" and a validator:

```python
    TELEGRAM_CHAT_ID: str = Field("", description="Telegram chat ID for notifications")
    TELEGRAM_MESSAGE_THREAD_ID: Optional[int] = Field(None, description="Telegram message thread ID for topics")
    SLACK_BOT_TOKEN: str = Field("", description="Slack bot token")

# ... down at the validators ...
    @field_validator("TELEGRAM_MESSAGE_THREAD_ID", mode="before")
    @classmethod
    def parse_thread_id(cls, v) -> Optional[int]:
        """Parse thread ID, treating empty strings as None."""
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        return int(v)
```

- [ ] **Step 2: Expose field in Core config**

In `finance_service/core/config.py`, under "Approval configuration":

```python
    APPROVAL_TIMEOUT = _pydantic_settings.APPROVAL_TIMEOUT
    TELEGRAM_BOT_TOKEN = _pydantic_settings.TELEGRAM_BOT_TOKEN
    TELEGRAM_CHAT_ID = _pydantic_settings.TELEGRAM_CHAT_ID
    TELEGRAM_MESSAGE_THREAD_ID = _pydantic_settings.TELEGRAM_MESSAGE_THREAD_ID
```

- [ ] **Step 3: Run project to ensure it doesn't crash**

Run: `python -c "from finance_service.core.config import Config; print(Config.TELEGRAM_MESSAGE_THREAD_ID)"`
Expected: `None` (or the integer if set in `.env`)

- [ ] **Step 4: Commit configuration updates**

```bash
git add finance_service/core/pydantic_config.py finance_service/core/config.py
git commit -m "feat: Add TELEGRAM_MESSAGE_THREAD_ID configuration"
```

### Task 3: Update Telegram Agent

**Files:**
- Modify: `finance_service/agents/telegram_agent.py`

- [ ] **Step 1: Load thread_id in initialization**

In `finance_service/agents/telegram_agent.py`, update `__init__`:

```python
        self.bot_token = config.get("telegram_bot_token", Config.TELEGRAM_BOT_TOKEN)
        self.chat_id = config.get("telegram_chat_id", Config.TELEGRAM_CHAT_ID)
        
        raw_thread_id = config.get("telegram_message_thread_id", Config.TELEGRAM_MESSAGE_THREAD_ID)
        self.thread_id = int(str(raw_thread_id).strip()) if raw_thread_id is not None and str(raw_thread_id).strip() != "" else None
```

- [ ] **Step 2: Update `send_message`**

Update the `bot_instance.send_message` call in `send_message`:

```python
        try:
            kwargs = {"chat_id": chat_id, "text": message, "parse_mode": parse_mode}
            if self.thread_id is not None:
                kwargs["message_thread_id"] = self.thread_id
            await self.bot_instance.send_message(**kwargs)
            logger.info(f"Message sent to chat ID: {chat_id}")
```

- [ ] **Step 3: Update `send_scheduled_report`**

Update the `bot_instance.send_message` call in `send_scheduled_report`:

```python
        try:
            kwargs = {"chat_id": target_chat_id, "text": message_text, "parse_mode": "Markdown"}
            if self.thread_id is not None:
                kwargs["message_thread_id"] = self.thread_id
            await self.bot_instance.send_message(**kwargs)
            logger.info(f"Scheduled report sent to chat ID: {target_chat_id}")
```

- [ ] **Step 4: Commit agent updates**

```bash
git add finance_service/agents/telegram_agent.py
git commit -m "feat: Support Telegram topics in TelegramAgent"
```

### Task 4: Update Approval Gate

**Files:**
- Modify: `finance_service/tools/approval_gate.py`

- [ ] **Step 1: Load thread_id in `TelegramApprovalGate.__init__`**

In `finance_service/tools/approval_gate.py`:

```python
        self.bot_token = bot_token or Config.TELEGRAM_BOT_TOKEN
        self.chat_id = chat_id or Config.TELEGRAM_CHAT_ID
        
        raw_thread_id = Config.TELEGRAM_MESSAGE_THREAD_ID
        self.thread_id = int(str(raw_thread_id).strip()) if raw_thread_id is not None and str(raw_thread_id).strip() != "" else None
```

- [ ] **Step 2: Update `send_approval_request`**

Update the `bot_instance.send_message` call:

```python
            kwargs = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }
            if self.thread_id is not None:
                kwargs["message_thread_id"] = self.thread_id

            await self.bot_instance.send_message(**kwargs)
```

- [ ] **Step 3: Commit approval gate updates**

```bash
git add finance_service/tools/approval_gate.py
git commit -m "feat: Support Telegram topics in ApprovalGate"
```