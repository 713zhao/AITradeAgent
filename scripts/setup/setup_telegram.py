#!/usr/bin/env python3
"""Get your Telegram chat ID - Run this and send any message to the bot."""
import asyncio
import logging
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

BOT_TOKEN = "8694519756:AAGxp6d7Fho3-696h4ae4tHvjcVmtazQUOw"

async def get_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Respond with chat ID."""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    user_name = update.effective_user.username or update.effective_user.first_name
    
    message = (
        f"✅ <b>Your Chat ID Found!</b>\n\n"
        f"📱 Chat ID: <code>{chat_id}</code>\n"
        f"👤 User ID: <code>{user_id}</code>\n"
        f"👥 Username: @{user_name}\n\n"
        f"<b>Add this to config/finance.yaml:</b>\n\n"
        f"<code>notifications:\n"
        f"  telegram:\n"
        f"    bot_token: \"{BOT_TOKEN}\"\n"
        f"    chat_id: \"{chat_id}\"</code>\n\n"
        f"Then restart the service!"
    )
    
    await context.bot.send_message(chat_id=chat_id, text=message, parse_mode="HTML")
    logger.info(f"✅ Chat ID: {chat_id}")
    print(f"\n{'='*60}")
    print(f"✅ YOUR CHAT ID: {chat_id}")
    print(f"{'='*60}\n")

async def main():
    logger.info("🤖 Telegram Setup - Waiting for message...")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT, get_chat_id))
    
    try:
        await app.run_polling()
    except KeyboardInterrupt:
        logger.info("🛑 Setup stopped")

if __name__ == "__main__":
    asyncio.run(main())
