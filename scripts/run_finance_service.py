#!/usr/bin/env python3
import os
import sys
import asyncio
import logging

# Add project root to path BEFORE any imports of finance_service
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def main():
    from finance_service.app import startup_orchestrator, create_app
    from hypercorn.config import Config as HypercornConfig
    from hypercorn.asyncio import serve
    
    logger.info("🔧 Initializing orchestrator...")
    await startup_orchestrator()
    logger.info("✅ Orchestrator initialized.")
    
    app = create_app()
    config = HypercornConfig()
    config.bind = [os.getenv("BIND", "0.0.0.0:8801")]
    config.worker_class = "uvloop"
    config.workers = 1
    config.accesslog = "-"
    config.errorlog = "-"
    
    logger.info("🚀 Starting ASGI server on %s", config.bind[0])
    try:
        await serve(app, config)
    except asyncio.CancelledError:
        logger.info("🛑 Server stopped")
    except Exception as e:
        logger.exception(f"❌ Server crashed: {e}")
        raise

def main_entry():
    logger.info("🚀 AiTradeAgent Finance Service")
    logger.info("📊 Market data: yfinance")
    logger.info("💰 Mode: PAPER")
    logger.info("🔌 Port: 8801")
    logger.info("🌐 Server: Hypercorn (ASGI)")
    logger.info("🔁 Auto-restart: disabled (use systemd/supervisor)")
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Service stopped by user")
        sys.exit(0)
    except SystemExit:
        raise
    except Exception as e:
        logger.exception(f"❌ Service crashed: {type(e).__name__}: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main_entry()
