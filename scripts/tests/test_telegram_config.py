#!/usr/bin/env python3
"""Test Telegram configuration."""
import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import logging
logging.basicConfig(level=logging.INFO)

async def main():
    from finance_service.core.yaml_config import YAMLConfigEngine
    from finance_service.core.config import Config
    from telegram import Bot
    
    print("\n" + "="*70)
    print("🤖 TELEGRAM BOT CONFIGURATION CHECK")
    print("="*70 + "\n")
    
    config_engine = YAMLConfigEngine(config_dir="config")
    
    bot_token = config_engine.get("notifications", "telegram/bot_token", default=None) or Config.TELEGRAM_BOT_TOKEN
    chat_id = config_engine.get("notifications", "telegram/chat_id", default=None) or Config.TELEGRAM_CHAT_ID
    is_enabled = config_engine.get("notifications", "telegram/enabled", default=True)
    
    print("📋 CONFIGURATION STATUS")
    print("-" * 70)
    print(f"  {'✅' if bot_token else '❌'} Bot Token:      {'Configured' if bot_token else 'NOT CONFIGURED'}")
    print(f"  {'✅' if chat_id else '❌'} Chat ID:        {'Configured' if chat_id else 'NOT CONFIGURED'}")
    print(f"  {'✅' if is_enabled else '❌'} Service:        {'ENABLED' if is_enabled else 'DISABLED'}")
    
    if not bot_token or not chat_id or not is_enabled:
        print("\n⚠️  SETUP INCOMPLETE - Follow these steps:")
        print("-" * 70)
        print("""
1. Run: python3 setup_telegram.py
2. Send ANY message to the bot in Telegram  
3. Copy the Chat ID from the response
4. Edit config/finance.yaml and update chat_id
5. Restart: python3 run_finance_service.py
""")
        return False
    
    print("\n🔌 TESTING CONNECTION...")
    print("-" * 70)
    
    try:
        bot = Bot(token=bot_token)
        user = await bot.get_me()
        print(f"  ✅ Bot token valid")
        print(f"     Bot: @{user.username}")
        print(f"  ✅ Configuration valid")
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False
    
    print("\n" + "="*70)
    print("✅ TELEGRAM SETUP COMPLETE!")
    print("="*70 + "\n")
    return True

if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
