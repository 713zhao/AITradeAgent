#!/usr/bin/env python3
"""
PicotradeAgent Finance Service Launcher
Forces yfinance provider and starts the Flask service
"""
import os
import sys
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
    
    try:
        # Import and run the Flask app
        from finance_service.app import app
        
        # Run on port 8801
        app.run(host='0.0.0.0', port=8801, debug=False, use_reloader=False)
        
    except KeyboardInterrupt:
        logger.info("🛑 Service stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Failed to start service: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()