import logging
import asyncio # Import asyncio
import time
from typing import Optional, Tuple, Dict, Any
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from ..core.config import Config

logger = logging.getLogger(__name__)

class ApprovalGate(ABC):
    """Base class for approval mechanisms"""
    
    def __init__(self, timeout: int = 300):
        self.timeout = timeout
        self.pending_approvals: Dict[str, asyncio.Event] = {}
        self.approval_responses: Dict[str, Tuple[bool, str]] = {}
    
    @abstractmethod
    async def send_approval_request(self, task_id: str, proposal: str,
                                 details: Dict[str, Any]) -> Tuple[bool, str]:
        """Send approval request to user"""
        pass
    
    @abstractmethod
    async def wait_for_response(self, task_id: str) -> Tuple[bool, str]:
        """Wait for approval response (YES/NO)"""
        pass
    
    async def request_approval(self, task_id: str, proposal_summary: str,
                            details: Dict[str, Any]) -> Tuple[bool, str, Optional[str]]:
        """
        Request human approval for a trade
        
        Returns:
            (approved, message, approval_id)
        """
        # Send request
        sent, msg = await self.send_approval_request(task_id, proposal_summary, details)
        if not sent:
            return False, f"Failed to send approval request: {msg}", None
        
        # Wait for response
        approved, response = await self.wait_for_response(task_id)
        
        if approved:
            approval_id = f"{task_id}_{int(time.time())}"
            return True, f"Approval confirmed: {response}", approval_id
        else:
            return False, f"Approval denied: {response}", None


class TelegramApprovalGate(ApprovalGate):
    """Telegram-based approval via python-telegram-bot"""
    
    def __init__(self, bot_token: str = None, chat_id: str = None):
        super().__init__(timeout=Config.APPROVAL_TIMEOUT)
        self.bot_token = bot_token or Config.TELEGRAM_BOT_TOKEN
        self.chat_id = chat_id or Config.TELEGRAM_CHAT_ID
        
        if not self.bot_token or not self.chat_id:
            logger.warning("Telegram credentials not configured")
            self.enabled = False
        else:
            self.enabled = True
        
        try:
            from telegram import Bot
            from telegram.error import TelegramError
            from telegram.ext import Updater, CommandHandler, MessageHandler, filters
            self.Bot = Bot
            self.TelegramError = TelegramError
            self.Updater = Updater
            self.CommandHandler = CommandHandler
            self.MessageHandler = MessageHandler
            self.filters = filters
            self.bot_instance = Bot(token=self.bot_token)

            # Setup updater and dispatcher
            self.updater = Updater(self.bot_token, use_context=True)
            self.dispatcher = self.updater.dispatcher

            # Register handlers
            self.dispatcher.add_handler(self.CommandHandler("start", self._start_command))
            self.dispatcher.add_handler(self.MessageHandler(self.filters.text & ~self.filters.command, self._handle_message))

            # Start polling in a separate thread
            self.updater.start_polling()
            logger.info("Telegram bot started polling.")

        except ImportError:
            logger.warning("python-telegram-bot not installed or incorrect version. Telegram approval gate disabled.")
            self.enabled = False
        except self.TelegramError as e:
            logger.error(f"Telegram bot initialization failed: {e}")
            self.enabled = False

    async def _start_command(self, update, context):
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Hi! I'm your Trade Approval Bot. Send YES or NO for approvals.")

    async def _handle_message(self, update, context):
        user_message = update.message.text.strip().upper()
        chat_id = update.effective_chat.id
        
        if str(chat_id) != self.chat_id:
            logger.warning(f"Received message from unauthorized chat ID: {chat_id}")
            await context.bot.send_message(chat_id=chat_id, text="Unauthorized chat.")
            return

        # Check if any pending approvals are awaiting a response
        # This logic needs to be enhanced to match the message to a specific task_id
        for task_id, event in self.pending_approvals.items():
            if user_message == "YES":
                self.approval_responses[task_id] = (True, "Approved by user")
                event.set() # Signal that a response has been received
                await context.bot.send_message(chat_id=chat_id, text=f"Approval for {task_id} confirmed.")
                break
            elif user_message == "NO":
                self.approval_responses[task_id] = (False, "Rejected by user")
                event.set() # Signal that a response has been received
                await context.bot.send_message(chat_id=chat_id, text=f"Approval for {task_id} denied.")
                break
        else:
            await context.bot.send_message(chat_id=chat_id, text="I don't understand that. No pending approvals matching your response.")

    async def send_approval_request(self, task_id: str, proposal: str,
                                 details: Dict[str, Any]) -> Tuple[bool, str]:
        """Send Telegram message with approval buttons"""
        if not self.enabled:
            logger.warning("Telegram approval gate not enabled")
            return False, "Telegram not configured"
        
        try:
            message = f"""🤖 **TRADE APPROVAL REQUIRED**\n\n**Proposal:** {proposal}\n\n**Details:**\n- Task ID: `{task_id}`\n- Created: {datetime.utcnow().isoformat()}\n- Timeout: {self.timeout}s\n\n**Risk Assessment:**\n{self._format_risk(details)}\n\nReply **YES** to execute or **NO** to cancel."""\n            
            # Store an asyncio.Event for this task_id and wait for it
            event = asyncio.Event()
            self.pending_approvals[task_id] = event
            self.approval_responses[task_id] = (False, "Timeout") # Default to timeout

            await self.bot_instance.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode="Markdown"
            )
            
            logger.info(f"Telegram approval request sent for {task_id}")
            return True, "Approval request sent via Telegram"
        
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {str(e)}")
            if task_id in self.pending_approvals:
                del self.pending_approvals[task_id]
            return False, str(e)
    
    async def wait_for_response(self, task_id: str) -> Tuple[bool, str]:
        """
        Wait for user response via Telegram. Asynchronously waits for an event to be set.
        """
        event = self.pending_approvals.get(task_id)
        if not event:
            return False, "No pending approval request found for this task ID."

        try:
            await asyncio.wait_for(event.wait(), timeout=self.timeout)
            approved, response_msg = self.approval_responses.get(task_id, (False, "No response"))
            return approved, response_msg
        except asyncio.TimeoutError:
            logger.warning(f"Approval timeout for task {task_id}")
            return False, f"Approval timeout after {self.timeout}s"
        finally:
            # Clean up pending approval after response or timeout
            if task_id in self.pending_approvals:
                del self.pending_approvals[task_id]
            if task_id in self.approval_responses:
                del self.approval_responses[task_id]
    
    @staticmethod
    def _format_risk(details: Dict[str, Any]) -> str:
        """Format risk details for message"""
        validation = details.get("validation", {})
        
        lines = []
        if validation.get("errors"):
            lines.append("⚠️ **Errors:**\n" + "\n".join(f"  - {e}" for e in validation["errors"]))
        if validation.get("warnings"):
            lines.append("⚠️ **Warnings:**\n" + "\n".join(f"  - {w}" for w in validation["warnings"]))
        
        return "\n".join(lines) or "✅ No constraints violated"


class SlackApprovalGate(ApprovalGate):
    """Slack-based approval"""
    
    async def send_approval_request(self, task_id: str, proposal: str,
                                 details: Dict[str, Any]) -> Tuple[bool, str]:
        """Send Slack message with approval options"""
        if not self.enabled:
            return False, "Slack not configured"
        
        try:
            from slack_sdk.web.async_client import AsyncWebClient
            self.client = AsyncWebClient(token=self.bot_token)

            message = f"""🤖 *TRADE APPROVAL REQUIRED*\n\n*Proposal:* {proposal}\n\nTask ID: `{task_id}`\nCreated: {datetime.utcnow().isoformat()}\n\nReply with *YES* or *NO*\n"""\n            
            response = await self.client.chat_postMessage(
                channel=self.channel,
                text=message
            )
            
            self.pending_approvals[task_id] = asyncio.Event()
            self.approval_responses[task_id] = (False, "Timeout")
            
            logger.info(f"Slack approval request sent for {task_id}")\n            return True, "Approval request sent via Slack"
        
        except Exception as e:\n            logger.error(f"Failed to send Slack message: {str(e)}")\n            return False, str(e)\n    \n    async def wait_for_response(self, task_id: str) -> Tuple[bool, str]:\n        \"\"\"Wait for response on Slack\"\"\"\n        event = self.pending_approvals.get(task_id)\n        if not event:\n            return False, \"No pending approval request found for this task ID.\"\n\n        try:\n            await asyncio.wait_for(event.wait(), timeout=self.timeout)\n            approved, response_msg = self.approval_responses.get(task_id, (False, \"No response\"))\n            return approved, response_msg\n        except asyncio.TimeoutError:\n            logger.warning(f\"Approval timeout for task {task_id}\")\n            return False, f\"Approval timeout after {self.timeout}s\"\n        finally:\n            if task_id in self.pending_approvals:\n                del self.pending_approvals[task_id]\n            if task_id in self.approval_responses:\n                del self.approval_responses[task_id]\n\n\nclass ManualApprovalGate(ApprovalGate):\n    \"\"\"Manual CLI-based approval for testing\"\"\"\n    \n    async def send_approval_request(self, task_id: str, proposal: str,\n                                 details: Dict[str, Any]) -> Tuple[bool, str]:\n        \"\"\"Display approval request in console\"\"\"\n        print(f\"\\n{'='*60}\")\n        print(f\"TRADE APPROVAL REQUIRED (Task: {task_id})\")\n        print(f\"{'='*60}\")\n        print(f\"\\nProposal: {proposal}\")\n        print(f\"\\nDetails:\")\n        for key, value in details.items():\n            print(f\"  {key}: {value}\")\n        print(f\"\\nTimeout: {self.timeout} seconds\")\n        print(f\"{'='*60}\\n\")\n        \n        self.pending_approvals[task_id] = asyncio.Event()\n        self.approval_responses[task_id] = (False, \"Timeout\") # Default to timeout\n        \n        return True, \"Approval request displayed\"\n    \n    async def wait_for_response(self, task_id: str) -> Tuple[bool, str]:\n        \"\"\"Wait for CLI input\"\"\"\n        start_time = time.time()\n        
        while time.time() - start_time < self.timeout:\n            try:\n                response = input(f\"Approve trade {task_id}? (YES/NO): \").strip().upper()\n                \n                if response == \"YES\":\n                    self.approval_responses[task_id] = (True, \"User approved via CLI\")\n                    self.pending_approvals[task_id].set()\n                    return True, \"User approved via CLI\"\n                elif response == \"NO\":\n                    self.approval_responses[task_id] = (False, \"User rejected via CLI\")\n                    self.pending_approvals[task_id].set()\n                    return False, \"User rejected via CLI\"\n                else:\n                    print(\"Please enter YES or NO\")\n            except Exception as e:\n                logger.error(f\"Error reading approval: {str(e)}\")\n            await asyncio.sleep(1) # Yield to event loop\n        \n        return False, f\"Approval timeout\"\n\n\nasync def get_approval_gate(gate_type: str = None) -> ApprovalGate:\n    \"\"\"\n    Factory function to get appropriate approval gate\n    \n    Args:\n        gate_type: \"telegram\", \"slack\", \"manual\", or auto-detect\n    \n    Returns:\n        ApprovalGate instance\n    \"\"\"\
    if gate_type == \"manual\":\n        return ManualApprovalGate()\n    elif gate_type == \"slack\" or (gate_type is None and Config.SLACK_BOT_TOKEN):\n        return SlackApprovalGate()\n    elif gate_type == \"telegram\" or (gate_type is None and Config.TELEGRAM_BOT_TOKEN):\n        return TelegramApprovalGate()\n    else:\n        logger.warning(\"No approval gate configured, using manual mode\")\n        return ManualApprovalGate()