import logging
import json
from typing import Dict, Any, Optional
import asyncio
from telegram import Bot
from telegram.error import TelegramError
from telegram.ext import Updater, CommandHandler, MessageHandler, filters, CallbackContext

from finance_service.agents.agent_interface import Agent, AgentReport
from finance_service.core.event_bus import Event, Events, get_event_bus
from finance_service.core.config import Config

logger = logging.getLogger(__name__)

class TelegramAgent(Agent):
    """Telegram Agent - Handles Telegram commands and sends reports."""

    @property
    def agent_id(self) -> str:
        return "telegram_agent"

    @property
    def goal(self) -> str:
        return "Provide a Telegram interface for interacting with the trading system and delivering scheduled reports."

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.event_bus = get_event_bus()
        self.bot_token = config.get("telegram_bot_token", Config.TELEGRAM_BOT_TOKEN)
        self.chat_id = config.get("telegram_chat_id", Config.TELEGRAM_CHAT_ID)
        
        if not self.bot_token or not self.chat_id:
            logger.warning("Telegram Agent not fully configured (missing token or chat ID). Disabling.")
            self.enabled = False
            self.updater = None
        else:
            self.enabled = True
            try:
                self.bot_instance = Bot(token=self.bot_token)
                self.updater = Updater(self.bot_token, use_context=True)
                self.dispatcher = self.updater.dispatcher

                # Register command handlers
                self.dispatcher.add_handler(CommandHandler("start", self._start_command))
                self.dispatcher.add_handler(CommandHandler("status", self._status_command))
                self.dispatcher.add_handler(CommandHandler("portfolio", self._portfolio_command))
                # Add more command handlers as needed

            except TelegramError as e:
                logger.error(f"Failed to initialize Telegram Bot: {e}")
                self.enabled = False
                self.updater = None

    async def run(self):
        if not self.enabled:
            logger.info("Telegram Agent is disabled due to missing configuration.")
            return
        logger.info(f"{self.agent_id} starting polling.")
        # Run the updater in a separate thread to not block the asyncio event loop
        # The handlers themselves should be async or dispatch to async tasks
        self.updater.start_polling()
        self.updater.idle() # This blocks the thread. In a real async app, this needs careful handling.
        # For now, we will rely on start_polling running in a separate thread.
        logger.info(f"{self.agent_id} polling stopped.")

    async def send_message(self, chat_id: str, message: str, parse_mode: Optional[str] = None):
        if not self.enabled:
            return
        try:
            await self.bot_instance.send_message(chat_id=chat_id, text=message, parse_mode=parse_mode)
            logger.info(f"Message sent to chat ID: {chat_id}")
        except TelegramError as e:
            logger.error(f"Failed to send message to {chat_id}: {e}")

    async def _start_command(self, update: Any, context: CallbackContext):
        if not self.enabled:
            return
        chat_id = update.effective_chat.id
        user = update.effective_user.mention_html()
        logger.info(f"Telegram Agent received /start command from {user} ({chat_id})")
        await self.send_message(chat_id, f"Hello {user}! I am your AI Trade Agent. How can I assist you?", parse_mode="HTML")

    async def _status_command(self, update: Any, context: CallbackContext):
        if not self.enabled:
            return
        chat_id = update.effective_chat.id
        logger.info(f"Telegram Agent received /status command from chat_id: {chat_id}")
        await self.event_bus.publish(Event(event_type=Events.GET_SYSTEM_STATUS, data={"chat_id": chat_id}))
        await self.send_message(chat_id, "Fetching system status...")

    async def _portfolio_command(self, update: Any, context: CallbackContext):
        if not self.enabled:
            return
        chat_id = update.effective_chat.id
        logger.info(f"Telegram Agent received /portfolio command from chat_id: {chat_id}")
        await self.event_bus.publish(Event(event_type=Events.GET_PORTFOLIO_STATE, data={"chat_id": chat_id}))
        await self.send_message(chat_id, "Fetching portfolio state...")

    async def send_scheduled_report(self, report_data: Dict[str, Any], chat_id: Optional[str] = None):
        if not self.enabled:
            return
        target_chat_id = chat_id if chat_id else self.chat_id
        if not target_chat_id:
            logger.error("Cannot send scheduled report: No chat_id provided or configured.")
            return

        message_text = f"**Daily Report**\n\n"
        for key, value in report_data.items():
            message_text += f"**{key}:** {value}\n"
        
        try:
            await self.bot_instance.send_message(chat_id=target_chat_id, text=message_text, parse_mode="Markdown")
            logger.info(f"Scheduled report sent to chat ID: {target_chat_id}")
        except TelegramError as e:
            logger.error(f"Failed to send scheduled report to {target_chat_id}: {e}")