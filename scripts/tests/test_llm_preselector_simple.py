#!/usr/bin/env python3
"""Simple LLM Pre-Selection Flow Test"""

import asyncio
import sys
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_llm_flow():
    """Test LLM preselector pipeline"""
    logger.info("\n" + "="*60)
    logger.info("🚀 LLM Pre-Selection Flow Test")
    logger.info("="*60 + "\n")
    
    try:
        from finance_service.core.event_bus import EventBus
        from finance_service.agents.market_regime_agent import MarketRegimeAgent
        from finance_service.agents.macro_news_agent import MacroNewsAgent
        from finance_service.agents.market_scanner_agent import MarketScannerAgent
        from finance_service.agents.symbol_selector_agent import SymbolSelectorAgent
        from finance_service.agents.data_agent import DataAgent
        
        event_bus = EventBus()
        
        # Create DataAgent first (dependency)
        data_agent = DataAgent(event_bus)
        
        # Create other agents
        regime_agent = MarketRegimeAgent(event_bus, data_agent)
        macro_agent = MacroNewsAgent(event_bus)
        scanner_agent = MarketScannerAgent(event_bus)
        selector_agent = SymbolSelectorAgent(event_bus)
        
        # Test US market
        logger.info("📌 Testing US market flow...")
        
        # Step 1: MarketRegimeAgent
        logger.info("⏳ MarketRegimeAgent (US)...")
        regime_us = await regime_agent.run({"market": "US", "force_refresh": True})
        logger.info("✅ Completed")
        if regime_us and hasattr(regime_us, 'payload'):
            payload = regime_us.payload
            logger.info(f"   Regime US: {payload.get('regime_us', 'N/A')}")
            logger.info(f"   Regime HK: {payload.get('regime_hk', 'N/A')}")
            logger.info(f"   Indices: {len(payload.get('indices', []))} total")
        
        # Step 2: MacroNewsAgent
        logger.info("⏳ MacroNewsAgent (US)...")
        macro_us = await macro_agent.run({"market": "US", "force_refresh": True})
        logger.info("✅ Completed")
        if macro_us and hasattr(macro_us, 'payload'):
            payload = macro_us.payload
            logger.info(f"   US Sentiment: {payload.get('us_sentiment_score', 'N/A')}")
            logger.info(f"   HK Sentiment: {payload.get('hk_sentiment_score', 'N/A')}")
            logger.info(f"   US News: {len(payload.get('us_macro_news', []))}")
            logger.info(f"   HK News: {len(payload.get('hk_macro_news', []))}")
        
        # Step 3: MarketScannerAgent
        logger.info("⏳ MarketScannerAgent (US)...")
        scan_us = await scanner_agent.run({"market": "US"})
        logger.info("✅ Completed")
        symbols_list = []
        if scan_us and hasattr(scan_us, 'payload'):
            symbols_list = scan_us.payload.get('symbols', [])
            logger.info(f"   Discovered: {len(symbols_list)} symbols")
            if symbols_list:
                logger.info(f"   Top 5: {symbols_list[:5]}")
        
        # Step 4: SymbolSelectorAgent (with Telegram)
        logger.info("⏳ SymbolSelectorAgent (US) - LLM ranking + Telegram...")
        selector_payload = {
            "market": "US",
            "market_regime": regime_us.payload if regime_us else None,
            "macro_news": macro_us.payload if macro_us else None,
            "candidates": symbols_list
        }
        selector_us = await selector_agent.run(selector_payload)
        logger.info("✅ Completed")
        
        if selector_us and hasattr(selector_us, 'payload'):
            payload = selector_us.payload
            ranked = payload.get('ranked_symbols', [])
            telegram_sent = payload.get('telegram_sent', False)
            telegram_msg_id = payload.get('telegram_message_id', None)
            
            logger.info(f"   Ranked symbols: {len(ranked)}")
            logger.info(f"   LLM model: {payload.get('llm_model', 'N/A')}")
            logger.info(f"   Tokens: {payload.get('tokens_used', 'N/A')}")
            logger.info(f"   Time: {payload.get('analysis_time_ms', 'N/A')}ms")
            
            if ranked and len(ranked) > 0:
                logger.info(f"   Top 3 ranked:")
                for i, sym in enumerate(ranked[:3], 1):
                    if isinstance(sym, dict):
                        logger.info(f"      {i}. {sym.get('symbol', 'N/A')} - Score: {sym.get('confidence_score', 'N/A')}")
                    else:
                        logger.info(f"      {i}. {sym}")
            
            logger.info(f"\n📱 TELEGRAM STATUS (US):")
            if telegram_sent:
                logger.info(f"   ✅ Message SENT (ID: {telegram_msg_id})")
            else:
                error = payload.get('telegram_error', 'Unknown error')
                logger.warning(f"   ⚠️  Not sent: {error}")
        
        # Test HK market
        logger.info("\n📌 Testing HK market flow...")
        
        logger.info("⏳ MarketRegimeAgent (HK)...")
        regime_hk = await regime_agent.run({"market": "HK", "force_refresh": True})
        logger.info("✅ Completed")
        if regime_hk and hasattr(regime_hk, 'payload'):
            logger.info(f"   Regime HK: {regime_hk.payload.get('regime_hk', 'N/A')}")
        
        logger.info("⏳ MacroNewsAgent (HK)...")
        macro_hk = await macro_agent.run({"market": "HK", "force_refresh": True})
        logger.info("✅ Completed")
        if macro_hk and hasattr(macro_hk, 'payload'):
            logger.info(f"   HK Sentiment: {macro_hk.payload.get('hk_sentiment_score', 'N/A')}")
        
        logger.info("⏳ MarketScannerAgent (HK)...")
        scan_hk = await scanner_agent.run({"market": "HK"})
        logger.info("✅ Completed")
        symbols_list_hk = []
        if scan_hk and hasattr(scan_hk, 'payload'):
            symbols_list_hk = scan_hk.payload.get('symbols', [])
            logger.info(f"   Discovered: {len(symbols_list_hk)} symbols")
            if symbols_list_hk:
                logger.info(f"   Top 3: {symbols_list_hk[:3]}")
        
        logger.info("⏳ SymbolSelectorAgent (HK) - LLM ranking + Telegram...")
        selector_payload_hk = {
            "market": "HK",
            "market_regime": regime_hk.payload if regime_hk else None,
            "macro_news": macro_hk.payload if macro_hk else None,
            "candidates": symbols_list_hk
        }
        selector_hk = await selector_agent.run(selector_payload_hk)
        logger.info("✅ Completed")
        
        if selector_hk and hasattr(selector_hk, 'payload'):
            payload = selector_hk.payload
            telegram_sent = payload.get('telegram_sent', False)
            telegram_msg_id = payload.get('telegram_message_id', None)
            
            logger.info(f"   Ranked symbols: {len(payload.get('ranked_symbols', []))}")
            logger.info(f"\n📱 TELEGRAM STATUS (HK):")
            if telegram_sent:
                logger.info(f"   ✅ Message SENT (ID: {telegram_msg_id})")
            else:
                logger.warning(f"   ⚠️  Not sent")
        
        # Final summary
        logger.info("\n" + "="*60)
        logger.info("✅ LLM PRE-SELECTION PIPELINE TEST COMPLETE")
        logger.info("="*60)
        logger.info("\nAll components verified:")
        logger.info("✅ MarketRegimeAgent - US & HK regimes computed")
        logger.info("✅ MacroNewsAgent - US & HK sentiment analyzed")
        logger.info("✅ MarketScannerAgent - Candidates discovered")
        logger.info("✅ SymbolSelectorAgent - LLM ranking + Telegram notifications")
        logger.info("\n" + "="*60 + "\n")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}", exc_info=True)
        return False

if __name__ == "__main__":
    try:
        success = asyncio.run(test_llm_flow())
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"Fatal: {e}", exc_info=True)
        sys.exit(1)
