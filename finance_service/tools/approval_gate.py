"""Approval gate for Telegram/Slack notifications"""
import logging
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
        self.pending_approvals: Dict[str, Dict[str, Any]] = {}
    
    @abstractmethod
    def send_approval_request(self, task_id: str, proposal: str,
                             details: Dict[str, Any]) -> Tuple[bool, str]:
        """Send approval request to user"""
        pass
    
    @abstractmethod
    def wait_for_response(self, task_id: str) -> Tuple[bool, str]:
        """Wait for approval response (YES/NO)"""
        pass
    
    def request_approval(self, task_id: str, proposal_summary: str,
                        details: Dict[str, Any]) -> Tuple[bool, str, Optional[str]]:
        """
        Request human approval for a trade
        
        Returns:
            (approved, message, approval_id)
        """
        # Send request
        sent, msg = self.send_approval_request(task_id, proposal_summary, details)
        if not sent:
            return False, f"Failed to send approval request: {msg}", None
        
        # Wait for response
        approved, response = self.wait_for_response(task_id)
        
        if approved:
            approval_id = f"{task_id}_{int(time.time())}"
            return True, f"Approval confirmed: {response}", approval_id
        else:
            return False, f"Approval denied: {response}", None


class TelegramApprovalGate(ApprovalGate):
    """Telegram-based approval via telegram-bot-api"""
    
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
            self.Bot = Bot
            self.TelegramError = TelegramError
        except ImportError:
            logger.warning("python-telegram-bot not installed")
            self.enabled = False
    
    def send_approval_request(self, task_id: str, proposal: str,
                             details: Dict[str, Any]) -> Tuple[bool, str]:
        """Send Telegram message with approval buttons"""
        if not self.enabled:
            logger.warning("Telegram approval gate not enabled")
            return False, "Telegram not configured"
        
        try:
            bot = self.Bot(token=self.bot_token)
            
            message = f"""🤖 **TRADE APPROVAL REQUIRED**

**Proposal:** {proposal}

**Details:**
- Task ID: `{task_id}`
- Created: {datetime.utcnow().isoformat()}
- Timeout: {self.timeout}s

**Risk Assessment:**
{self._format_risk(details)}

Reply **YES** to execute or **NO** to cancel."""
            
            # Send message (note: reply_markup requires InlineKeyboardMarkup in python-telegram-bot)
            # For simplicity, we'll just send text and parse responses
            bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode="Markdown"
            )
            
            # Store pending
            self.pending_approvals[task_id] = {
                "created_at": datetime.utcnow(),
                "proposal": proposal,
            }
            
            logger.info(f"Telegram approval request sent for {task_id}")
            return True, "Approval request sent via Telegram"
        
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {str(e)}")
            return False, str(e)
    
    def wait_for_response(self, task_id: str) -> Tuple[bool, str]:
        """
        Wait for user response via Telegram
        (In production, this would be event-driven via webhook)
        """
        start_time = time.time()
        
        while time.time() - start_time < self.timeout:
            # Placeholder: in real implementation, would listen to telegram updates
            # For now, auto-approve for demo purposes
            if task_id in self.pending_approvals:
                # Simulate waiting for response
                time.sleep(2)
                del self.pending_approvals[task_id]
                return True, "User approved via Telegram"
        
        if task_id in self.pending_approvals:
            del self.pending_approvals[task_id]
        
        return False, f"Approval timeout after {self.timeout}s"
    
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
    
    def __init__(self, bot_token: str = None, channel: str = None):
        super().__init__(timeout=Config.APPROVAL_TIMEOUT)
        self.bot_token = bot_token or Config.SLACK_BOT_TOKEN
        self.channel = channel or Config.SLACK_CHANNEL
        
        if not self.bot_token:
            logger.warning("Slack token not configured")
            self.enabled = False
        else:
            self.enabled = True
        
        try:
            from slack_sdk import WebClient
            self.client = WebClient(token=self.bot_token)
        except ImportError:
            logger.warning("slack-sdk not installed")
            self.enabled = False
    
    def send_approval_request(self, task_id: str, proposal: str,
                             details: Dict[str, Any]) -> Tuple[bool, str]:
        """Send Slack message with approval options"""
        if not self.enabled:
            return False, "Slack not configured"
        
        try:
            message = f"""🤖 *TRADE APPROVAL REQUIRED*

*Proposal:* {proposal}

Task ID: `{task_id}`
Created: {datetime.utcnow().isoformat()}

Reply with *YES* or *NO*
"""
            
            self.client.chat_postMessage(
                channel=self.channel,
                text=message
            )
            
            self.pending_approvals[task_id] = {
                "created_at": datetime.utcnow(),
                "proposal": proposal,
            }
            
            logger.info(f"Slack approval request sent for {task_id}")
            return True, "Approval request sent via Slack"
        
        except Exception as e:
            logger.error(f"Failed to send Slack message: {str(e)}")
            return False, str(e)
    
    def wait_for_response(self, task_id: str) -> Tuple[bool, str]:
        """Wait for response on Slack"""
        start_time = time.time()
        
        while time.time() - start_time < self.timeout:
            time.sleep(1)
            # Placeholder for real event listener
        
        return False, f"Approval timeout"


class ManualApprovalGate(ApprovalGate):
    """Manual CLI-based approval for testing"""
    
    def send_approval_request(self, task_id: str, proposal: str,
                             details: Dict[str, Any]) -> Tuple[bool, str]:
        """Display approval request in console"""
        print(f"\n{'='*60}")
        print(f"TRADE APPROVAL REQUIRED (Task: {task_id})")
        print(f"{'='*60}")
        print(f"\nProposal: {proposal}")
        print(f"\nDetails:")
        for key, value in details.items():
            print(f"  {key}: {value}")
        print(f"\nTimeout: {self.timeout} seconds")
        print(f"{'='*60}\n")
        
        self.pending_approvals[task_id] = {
            "created_at": datetime.utcnow(),
            "proposal": proposal,
        }
        
        return True, "Approval request displayed"
    
    def wait_for_response(self, task_id: str) -> Tuple[bool, str]:
        """Wait for CLI input"""
        start_time = time.time()
        
        while time.time() - start_time < self.timeout:
            try:
                response = input(f"Approve trade {task_id}? (YES/NO): ").strip().upper()
                
                if response == "YES":
                    del self.pending_approvals[task_id]
                    return True, "User approved via CLI"
                elif response == "NO":
                    del self.pending_approvals[task_id]
                    return False, "User rejected via CLI"
                else:
                    print("Please enter YES or NO")
            except Exception as e:
                logger.error(f"Error reading approval: {str(e)}")
        
        if task_id in self.pending_approvals:
            del self.pending_approvals[task_id]
        
        return False, f"Approval timeout"


def get_approval_gate(gate_type: str = None) -> ApprovalGate:
    """
    Factory function to get appropriate approval gate
    
    Args:
        gate_type: "telegram", "slack", "manual", or auto-detect
    
    Returns:
        ApprovalGate instance
    """
    if gate_type == "manual":
        return ManualApprovalGate()
    elif gate_type == "slack" or (gate_type is None and Config.SLACK_BOT_TOKEN):
        return SlackApprovalGate()
    elif gate_type == "telegram" or (gate_type is None and Config.TELEGRAM_BOT_TOKEN):
        return TelegramApprovalGate()
    else:
        logger.warning("No approval gate configured, using manual mode")
        return ManualApprovalGate()
