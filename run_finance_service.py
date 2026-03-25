#!/usr/bin/env python3
"""
PicotradeAgent Finance Service Launcher
Forces yfinance provider and starts the Flask service with Hypercorn (ASGI)
"""
import os
import sys
import asyncio
import subprocess
import time
import signal
import logging

# Set environment variables before any imports
os.environ['OPENBB_USE_YFINANCE'] = 'true'
os.environ['OPENBB_PROVIDER'] = 'yfinance'
os.environ['FLASK_ENV'] = 'production'
os.environ['PYTHONUNBUFFERED'] = '1'
os.environ['LOG_LEVEL'] = 'INFO'

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    """Start the finance service"""
    logger.info("🚀 Starting PicotradeAgent Finance Service...")
    logger.info("📊 Market data source: yfinance (free)")
    logger.info("💰 Trading mode: PAPER (simulated)")
    logger.info("🔌 Port: 8801")
    logger.info("🌐 Server: Hypercorn (ASGI)")
    
    try:
        # Import the Flask app and run with Hypercorn (ASGI server for async Flask)
        from finance_service.app import app, startup_orchestrator
        from hypercorn.asyncio import serve
        from hypercorn.config import Config
        
        async def async_main():
            # Initialize orchestrator before starting server
            logger.info("🔧 Initializing orchestrator...")
            await startup_orchestrator()
            logger.info("✅ Orchestrator initialized")
            
            # Configure Hypercorn
            hypercorn_config = Config()
            hypercorn_config.bind = ["0.0.0.0:8801"]
            hypercorn_config.loglevel = "info"
            hypercorn_config.accesslog = "-"
            
            # Run the async server
            logger.info("🌐 Starting server on http://0.0.0.0:8801")
            await serve(app, hypercorn_config)
        
        # Run the combined async main
        asyncio.run(async_main())
        
    except KeyboardInterrupt:
        logger.info("🛑 Service stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Failed to start service: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()