#!/usr/bin/env python3
"""
Test LLM Pre-Selection Flow
Triggers: PRE_SCAN_CONTEXT_REFRESH -> MarketRegimeAgent + MacroNewsAgent -> MARKET_SCAN_TRIGGER -> SymbolSelectorAgent
Verifies: Results sent to Telegram
"""

import asyncio
import sys
import os
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from finance_service.core.event_bus import EventBus, Event, Events
from finance_service.agents.market_regime_agent import MarketRegimeAgent
from finance_service.agents.macro_news_agent import MacroNewsAgent
from finance_service.agents.market_scanner_agent import MarketScannerAgent
from finance_service.agents.symbol_selector_agent import SymbolSelectorAgent
from finance_service.agents.scheduler_agent import SchedulerAgent
from finance_service.app import MainOrchestratorAgent
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class LLMPreselectorFlowTester:
    def __init__(self):
        self.event_bus = EventBus()
        self.market_regime_agent = MarketRegimeAgent(self.event_bus)
        self.macro_news_agent = MacroNewsAgent(self.event_bus)
        self.market_scanner_agent = MarketScannerAgent(self.event_bus)
        self.symbol_selector_agent = SymbolSelectorAgent(self.event_bus)
        self.scheduler_agent = SchedulerAgent(self.event_bus)
        
        # Track events
        self.events_received = []
        self.regime_result = None
        self.macro_result = None
        self.scan_result = None
        self.selector_result = None
        
    async def setup_event_listeners(self, market: str):
        """Setup listeners to track event flow"""
        
        async def track_event(event: Event):
            self.events_received.append({
                'timestamp': datetime.now(),
                'event_type': event.event_type,
                'data': str(event.data)[:200] if event.data else None
            })
            logger.info(f"📍 Event received: {event.event_type}")
        
        # Subscribe to key events
        self.event_bus.subscribe(Events.PRE_SCAN_CONTEXT_REFRESH, track_event)
        self.event_bus.subscribe(Events.MARKET_SCAN_TRIGGER, track_event)
        self.event_bus.subscribe(Events.MARKET_SCANNED, track_event)
        self.event_bus.subscribe("LLM_RANKING_COMPLETE", track_event)
        
    async def run_test(self, market: str = "US"):
        """Execute full LLM pre-selection flow"""
        
        logger.info(f"\n{'='*60}")
        logger.info(f"🚀 Starting LLM Pre-Selection Flow for {market} market")
        logger.info(f"{'='*60}\n")
        
        # Setup listeners
        await self.setup_event_listeners(market)
        
        try:
            # Step 1: Trigger PRE_SCAN_CONTEXT_REFRESH
            logger.info(f"\n📌 STEP 1: Triggering PRE_SCAN_CONTEXT_REFRESH for {market}")
            logger.info(f"   Purpose: Pre-warm MarketRegimeAgent + MacroNewsAgent caches")
            
            pre_scan_event = Event(
                event_type=Events.PRE_SCAN_CONTEXT_REFRESH,
                data={"market": market, "force_refresh": True}
            )
            await self.event_bus.publish(pre_scan_event)
            
            # Run MarketRegimeAgent + MacroNewsAgent in parallel (pre-warming)
            logger.info(f"\n⏳ Running MarketRegimeAgent + MacroNewsAgent (parallel pre-warm)...")
            
            try:
                regime_task = self.market_regime_agent.run({
                    "market": market,
                    "force_refresh": True
                })
                macro_task = self.macro_news_agent.run({
                    "market": market,
                    "force_refresh": True
                })
                
                results = await asyncio.gather(regime_task, macro_task, return_exceptions=True)
                
                if isinstance(results[0], Exception):
                    logger.error(f"❌ MarketRegimeAgent failed: {results[0]}")
                else:
                    self.regime_result = results[0]
                    logger.info(f"✅ MarketRegimeAgent completed")
                    if results[0] and hasattr(results[0], 'payload'):
                        regime_data = results[0].payload
                        logger.info(f"   Regime: {regime_data.get('regime', 'N/A')}")
                        logger.info(f"   Regime US: {regime_data.get('regime_us', 'N/A')}")
                        logger.info(f"   Regime HK: {regime_data.get('regime_hk', 'N/A')}")
                
                if isinstance(results[1], Exception):
                    logger.error(f"❌ MacroNewsAgent failed: {results[1]}")
                else:
                    self.macro_result = results[1]
                    logger.info(f"✅ MacroNewsAgent completed")
                    if results[1] and hasattr(results[1], 'payload'):
                        macro_data = results[1].payload
                        logger.info(f"   US Sentiment: {macro_data.get('us_sentiment_score', 'N/A')}")
                        logger.info(f"   HK Sentiment: {macro_data.get('hk_sentiment_score', 'N/A')}")
            
            except Exception as e:
                logger.error(f"❌ Error during pre-warming: {e}", exc_info=True)
            
            # Step 2: Wait a bit then trigger MARKET_SCAN_TRIGGER
            logger.info(f"\n⏳ Waiting 5 seconds for cache to warm...")
            await asyncio.sleep(5)
            
            logger.info(f"\n📌 STEP 2: Triggering MARKET_SCAN_TRIGGER")
            logger.info(f"   Purpose: Discover {market} market candidates")
            
            market_scan_event = Event(
                event_type=Events.MARKET_SCAN_TRIGGER,
                data={"market": market, "interval": "pre_market"}
            )
            await self.event_bus.publish(market_scan_event)
            
            # Step 3: Run MarketScannerAgent
            logger.info(f"\n⏳ Running MarketScannerAgent for {market}...")
            
            try:
                scan_result = await self.market_scanner_agent.run({
                    "market": market
                })
                self.scan_result = scan_result
                logger.info(f"✅ MarketScannerAgent completed")
                
                if scan_result and hasattr(scan_result, 'payload'):
                    symbols = scan_result.payload.get('symbols', [])
                    logger.info(f"   Discovered symbols: {len(symbols)}")
                    if symbols:
                        logger.info(f"   Top 5 symbols: {symbols[:5]}")
            except Exception as e:
                logger.error(f"❌ MarketScannerAgent failed: {e}", exc_info=True)
            
            # Step 4: Run SymbolSelectorAgent (LLM ranking)
            logger.info(f"\n📌 STEP 3: Running SymbolSelectorAgent (LLM pre-selection)")
            logger.info(f"   Purpose: Rank candidates via LLM, select top 5-10")
            
            try:
                # Prepare payload with regime + macro context
                selector_payload = {
                    "market": market,
                    "market_regime": self.regime_result.payload if self.regime_result else None,
                    "macro_news": self.macro_result.payload if self.macro_result else None,
                }
                
                if self.scan_result and hasattr(self.scan_result, 'payload'):
                    selector_payload["candidates"] = self.scan_result.payload.get('symbols', [])
                
                selector_result = await self.symbol_selector_agent.run(selector_payload)
                self.selector_result = selector_result
                logger.info(f"✅ SymbolSelectorAgent completed")
                
                if selector_result and hasattr(selector_result, 'payload'):
                    payload = selector_result.payload
                    logger.info(f"\n🏆 LLM RANKING RESULTS for {market}:")
                    logger.info(f"   Total ranked symbols: {len(payload.get('ranked_symbols', []))}")
                    logger.info(f"   LLM model: {payload.get('llm_model', 'N/A')}")
                    logger.info(f"   Tokens used: {payload.get('tokens_used', 'N/A')}")
                    logger.info(f"   Analysis time: {payload.get('analysis_time_ms', 'N/A')}ms")
                    
                    ranked = payload.get('ranked_symbols', [])
                    if ranked:
                        logger.info(f"\n   Top 5 ranked symbols:")
                        for i, sym in enumerate(ranked[:5], 1):
                            score = sym.get('confidence_score', 0) if isinstance(sym, dict) else 'N/A'
                            reason = sym.get('reason', '') if isinstance(sym, dict) else ''
                            logger.info(f"      {i}. {sym if isinstance(sym, str) else sym.get('symbol', 'N/A')} - Score: {score}")
                            if reason:
                                logger.info(f"         {reason[:80]}")
                    
                    # Check if Telegram message was sent
                    telegram_status = payload.get('telegram_sent', False)
                    if telegram_status:
                        logger.info(f"\n✅ Telegram notification SENT")
                        logger.info(f"   Message ID: {payload.get('telegram_message_id', 'N/A')}")
                    else:
                        logger.warning(f"\n⚠️  Telegram notification not sent")
                        
            except Exception as e:
                logger.error(f"❌ SymbolSelectorAgent failed: {e}", exc_info=True)
            
            # Final Summary
            logger.info(f"\n{'='*60}")
            logger.info(f"✅ TEST SUMMARY")
            logger.info(f"{'='*60}")
            logger.info(f"Market: {market}")
            logger.info(f"Total events published: {len(self.events_received)}")
            logger.info(f"Regime agent: {'✅ Passed' if self.regime_result else '❌ Failed'}")
            logger.info(f"Macro news agent: {'✅ Passed' if self.macro_result else '❌ Failed'}")
            logger.info(f"Scanner agent: {'✅ Passed' if self.scan_result else '❌ Failed'}")
            logger.info(f"Selector agent: {'✅ Passed' if self.selector_result else '❌ Failed'}")
            
            if self.selector_result and hasattr(self.selector_result, 'payload'):
                telegram_sent = self.selector_result.payload.get('telegram_sent', False)
                logger.info(f"Telegram sent: {'✅ Yes' if telegram_sent else '❌ No'}")
            
            logger.info(f"{'='*60}\n")
            
        except Exception as e:
            logger.error(f"\n❌ Critical error: {e}", exc_info=True)
            return False
        
        return True


async def main():
    """Main test runner"""
    tester = LLMPreselectorFlowTester()
    
    # Test US market
    await tester.run_test(market="US")
    
    # Optionally test HK market
    logger.info("\n" + "="*60)
    logger.info("Testing HK market...")
    logger.info("="*60 + "\n")
    
    tester2 = LLMPreselectorFlowTester()
    await tester2.run_test(market="HK")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n\n⏹️  Test interrupted by user")
    except Exception as e:
        logger.error(f"\n\n❌ Fatal error: {e}", exc_info=True)
        sys.exit(1)
