import logging
import asyncio
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
        pass
    
    @abstractmethod
    async def wait_for_response(self, task_id: str) -> Tuple[bool, str]:
        pass


class TelegramApprovalGate(ApprovalGate):
    """Telegram-based approval with clickable YES/NO buttons"""
    
    def __init__(self, bot_token: str = None, chat_id: str = None):
        super().__init__(timeout=Config.APPROVAL_TIMEOUT)
        self.bot_token = bot_token or Config.TELEGRAM_BOT_TOKEN
        self.chat_id = chat_id or Config.TELEGRAM_CHAT_ID
        self.enabled = False
        self.bot_instance = None
        
        if not self.bot_token or not self.chat_id:
            logger.warning("Telegram credentials not configured")
            return
        
        try:
            from telegram import Bot
            self.bot_instance = Bot(token=self.bot_token)
            self.enabled = True
            logger.info("✅ Telegram bot initialized with button support")
        except Exception as e:
            logger.error(f"Failed to initialize Telegram bot: {e}")
    
    async def send_approval_request(self, task_id: str, proposal: str,
                                   details: Dict[str, Any]) -> Tuple[bool, str]:
        
        if not self.enabled:
            return False, "Telegram not configured"
        
        try:
            from telegram import InlineKeyboardMarkup, InlineKeyboardButton
            
            confidence = details.get('confidence', 0)
            violations = details.get('violations', [])
            
            # Format message
            msg_text = "🤖 **TRADE APPROVAL REQUIRED**\n\n"
            msg_text += f"**Proposal:** {proposal}\n\n"
            msg_text += "**Details:**\n"
            msg_text += f"• Task: `{task_id}`\n"
            msg_text += f"• Confidence: {confidence*100:.1f}%\n"
            msg_text += f"• Timeout: {self.timeout}s\n"
            
            if violations:
                msg_text += f"\n**Risk Issues:**\n"
                for v in violations[:3]:
                    msg_text += f"  • {v}\n"
            
            msg_text += f"\n👇 **Click a button below to respond:**"
            
            logger.info(f"Sending Telegram approval for {task_id}")
            
            # Create inline keyboard with YES and NO buttons
            keyboard = [
                [
                    InlineKeyboardButton("✅ YES - APPROVE", callback_data=f"approve_{task_id}"),
                    InlineKeyboardButton("❌ NO - REJECT", callback_data=f"reject_{task_id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Send message with buttons
            await self.bot_instance.send_message(
                chat_id=self.chat_id,
                text=msg_text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
            
            # Setup event for response
            event = asyncio.Event()
            self.pending_approvals[task_id] = event
            self.approval_responses[task_id] = (False, "Timeout")
            
            logger.info(f"✅ Telegram message with YES/NO buttons sent for {task_id}")
            return True, "Approval request sent - click the buttons in Telegram"
        
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False, str(e)
    
    async def wait_for_response(self, task_id: str) -> Tuple[bool, str]:
        """Wait for response by polling Telegram getUpdates for callback queries."""
        event = self.pending_approvals.get(task_id)
        if not event:
            return False, "No approval found"

        try:
            import urllib.request as _ureq
            import urllib.parse as _uparse
            import json as _json

            offset = None
            start = time.time()
            while time.time() - start < self.timeout:
                # Poll Telegram for any incoming callback queries
                try:
                    params = {"timeout": 2, "allowed_updates": '["callback_query"]'}
                    if offset is not None:
                        params["offset"] = offset
                    url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates?" + _uparse.urlencode(params)
                    req = _ureq.Request(url, method="GET")
                    with _ureq.urlopen(req, timeout=5) as resp:
                        updates = _json.loads(resp.read().decode())
                    if updates.get("ok") and updates.get("result"):
                        for update in updates["result"]:
                            offset = update["update_id"] + 1  # advance offset to ack
                            cb = update.get("callback_query", {})
                            data = cb.get("data", "")
                            # Answer the callback to dismiss the "loading" spinner
                            try:
                                ack_url = f"https://api.telegram.org/bot{self.bot_token}/answerCallbackQuery"
                                ack_data = _uparse.urlencode({"callback_query_id": cb["id"]}).encode()
                                _ureq.urlopen(_ureq.Request(ack_url, data=ack_data, method="POST"), timeout=5)
                            except Exception:
                                pass
                            if data == f"approve_{task_id}":
                                self.approval_responses[task_id] = (True, "Approved via Telegram button")
                                event.set()
                                logger.info(f"Trade {task_id} APPROVED via Telegram button")
                                return True, "Approved via Telegram button"
                            elif data == f"reject_{task_id}":
                                self.approval_responses[task_id] = (False, "Rejected via Telegram button")
                                event.set()
                                logger.info(f"Trade {task_id} REJECTED via Telegram button")
                                return False, "Rejected via Telegram button"
                except Exception as e:
                    logger.debug(f"getUpdates poll error: {e}")
                await asyncio.sleep(1)

            logger.warning(f"Approval timeout for {task_id} after {self.timeout}s")
            return False, "Timeout - no response received"

        finally:
            if task_id in self.pending_approvals:
                del self.pending_approvals[task_id]
            if task_id in self.approval_responses:
                del self.approval_responses[task_id]


class ManualApprovalGate(ApprovalGate):
    """Manual CLI approval """
    
    async def send_approval_request(self, task_id: str, proposal: str,
                                   details: Dict[str, Any]) -> Tuple[bool, str]:
        
        print(f"\n{'='*60}")
        print(f"✋ APPROVAL REQUIRED")
        print(f"{'='*60}")
        print(f"Proposal: {proposal}")
        print(f"Task: {task_id}")
        for k, v in details.items():
            print(f"  {k}: {v}")
        print(f"{'='*60}\n")
        
        self.pending_approvals[task_id] = asyncio.Event()
        self.approval_responses[task_id] = (False, "Timeout")
        return True, "Displayed in CLI"
    
    async def wait_for_response(self, task_id: str) -> Tuple[bool, str]:
        
        start = time.time()
        while time.time() - start < self.timeout:
            try:
                response = input(f"Enter YES or NO: ").strip().upper()
                if response == "YES":
                    return True, "Approved via CLI"
                elif response == "NO":
                    return False, "Rejected via CLI"
                else:
                    print("Please enter YES or NO")
            except Exception as e:
                logger.error(f"Error: {e}")
            await asyncio.sleep(1)
        
        return False, "Timeout"


def get_approval_gate(gate_type: str = None) -> ApprovalGate:
    """Get approval gate instance"""
    
    if gate_type == "manual":
        return ManualApprovalGate()
    elif gate_type == "telegram" or (gate_type is None and Config.TELEGRAM_BOT_TOKEN):
        return TelegramApprovalGate()
    else:
        return ManualApprovalGate()
