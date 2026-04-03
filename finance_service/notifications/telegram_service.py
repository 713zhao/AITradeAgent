"""
Enhanced Telegram Notification Service
Sends trading notifications for executed trades, closed positions, and daily summaries.
"""
import logging
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime
from telegram import Bot
from telegram.error import TelegramError

logger = logging.getLogger(__name__)

class TelegramNotificationService:
    """Service for sending trading notifications via Telegram."""

    def __init__(self, bot_token: str, chat_id: str, message_thread_id: Optional[int] = None):
        """Initialize Telegram notification service."""
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.message_thread_id = message_thread_id
        self.bot = Bot(token=bot_token)
        self._message_queue = asyncio.Queue()
        self._is_running = False

    async def start(self):
        """Start the notification service."""
        if self._is_running:
            logger.warning("Notification service already running")
            return
        
        self._is_running = True
        logger.info(f"🚀 Telegram Notification Service started (Chat: {self.chat_id})")
        asyncio.create_task(self._process_messages())

    async def stop(self):
        """Stop the notification service."""
        self._is_running = False

    async def send_notification(self, message: str, parse_mode: str = "HTML"):
        """Queue a notification message."""
        await self._message_queue.put({
            "message": message,
            "parse_mode": parse_mode,
            "timestamp": datetime.now()
        })

    async def send_trade_notification(self, trade_info: Dict[str, Any]):
        """Send notification for executed trade."""
        symbol = trade_info.get("symbol", "UNKNOWN")
        action = trade_info.get("action", "UNKNOWN")
        quantity = trade_info.get("quantity", 0)
        entry_price = trade_info.get("entry_price", 0)
        target_price = trade_info.get("target_price", 0)
        stop_loss = trade_info.get("stop_loss", 0)
        confidence = trade_info.get("confidence", 0)
        reason = trade_info.get("reason", "")

        if action.upper() == "BUY":
            potential_profit = (target_price - entry_price) * quantity
            potential_gain_pct = ((target_price - entry_price) / entry_price * 100) if entry_price > 0 else 0
            emoji = "📈"
        else:
            potential_profit = (entry_price - target_price) * quantity
            potential_gain_pct = ((entry_price - target_price) / entry_price * 100) if entry_price > 0 else 0
            emoji = "📉"

        message = f"""
{emoji} <b>TRADE EXECUTED</b>

<b>Symbol:</b> {symbol}
<b>Action:</b> {action.upper()}
<b>Quantity:</b> {quantity}
<b>Entry Price:</b> ${entry_price:.2f}
<b>Target Price:</b> ${target_price:.2f}
<b>Stop Loss:</b> ${stop_loss:.2f}
<b>Confidence:</b> {confidence:.1%}

💰 <b>Potential Profit:</b> ${potential_profit:.2f} ({potential_gain_pct:+.2f}%)

📝 <b>Reason:</b>
{reason}

<i>Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>
"""
        await self.send_notification(message)

    async def send_position_closed_notification(self, trade_info: Dict[str, Any]):
        """Send notification for closed position."""
        symbol = trade_info.get("symbol", "UNKNOWN")
        action = trade_info.get("action", "UNKNOWN")
        entry_price = trade_info.get("entry_price", 0)
        exit_price = trade_info.get("exit_price", 0)
        quantity = trade_info.get("quantity", 0)
        profit_loss = trade_info.get("profit_loss", 0)
        profit_loss_pct = trade_info.get("profit_loss_pct", 0)

        emoji = "✅" if profit_loss >= 0 else "❌"
        prefix = "PROFIT" if profit_loss >= 0 else "LOSS"

        message = f"""
{emoji} <b>POSITION CLOSED - {prefix}</b>

<b>Symbol:</b> {symbol}
<b>Direction:</b> {action.upper()}
<b>Entry Price:</b> ${entry_price:.2f}
<b>Exit Price:</b> ${exit_price:.2f}
<b>Quantity:</b> {quantity}

💵 <b>P&L:</b> ${profit_loss:+.2f} ({profit_loss_pct:+.2f}%)

<i>Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>
"""
        await self.send_notification(message)

    async def send_error_notification(self, error_info: Dict[str, Any]):
        """Send error/alert notification."""
        error_type = error_info.get("error_type", "UNKNOWN")
        message_text = error_info.get("message", "")
        details = error_info.get("details", "")

        message = f"""
⚠️ <b>ALERT: {error_type}</b>

<b>Message:</b>
{message_text}

<b>Details:</b>
{details}

<i>Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>
"""
        await self.send_notification(message)

    async def _process_messages(self):
        """Process and send queued messages."""
        while self._is_running:
            try:
                message_data = await asyncio.wait_for(self._message_queue.get(), timeout=1.0)
                await self._send_message(message_data["message"], message_data["parse_mode"])
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error processing message: {e}")

    async def _send_message(self, text: str, parse_mode: str = "HTML"):
        """Send message via Telegram bot."""
        try:
            kwargs = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": parse_mode
            }
            if self.message_thread_id:
                kwargs["message_thread_id"] = self.message_thread_id
            
            await self.bot.send_message(**kwargs)
            logger.debug(f"Message sent to chat {self.chat_id}")
        except TelegramError as e:
            logger.error(f"Failed to send Telegram message: {e}")
        except Exception as e:
            logger.error(f"Unexpected error sending message: {e}")


async def get_or_create_notification_service() -> Optional[TelegramNotificationService]:
    """Get or create Telegram notification service based on config."""
    from finance_service.core.yaml_config import YAMLConfigEngine
    from finance_service.core.config import Config
    
    config_engine = YAMLConfigEngine(config_dir="config")
    
    bot_token = config_engine.get("notifications", "telegram/bot_token", default=None)
    chat_id = config_engine.get("notifications", "telegram/chat_id", default=None)
    is_enabled = config_engine.get("notifications", "telegram/enabled", default=True)
    
    if not bot_token:
        bot_token = Config.TELEGRAM_BOT_TOKEN
    if not chat_id:
        chat_id = Config.TELEGRAM_CHAT_ID
    
    if not is_enabled or not bot_token or not chat_id:
        logger.warning(f"Telegram notifications not configured. Token: {'✓' if bot_token else '✗'}, Chat: {'✓' if chat_id else '✗'}")
        return None
    
    message_thread_id = config_engine.get("notifications", "telegram/message_thread_id", default=None)
    if message_thread_id:
        try:
            message_thread_id = int(message_thread_id)
        except (ValueError, TypeError):
            message_thread_id = None
    
    service = TelegramNotificationService(
        bot_token=bot_token,
        chat_id=chat_id,
        message_thread_id=message_thread_id
    )
    
    logger.info("✅ Telegram Notification Service initialized")
    return service
