#!/usr/bin/env python3
"""
Simple launcher: Flask in main thread, orchestrator in a daemon asyncio thread.
"""
import os
import sys
import threading
import asyncio
import logging

# Set env before imports
os.environ['OPENBB_USE_YFINANCE'] = 'true'
os.environ['OPENBB_PROVIDER'] = 'yfinance'
os.environ['FLASK_ENV'] = 'production'
os.environ['PYTHONUNBUFFERED'] = '1'
os.environ['LOG_LEVEL'] = 'INFO'

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def start_orchestrator():
    """Run orchestrator startup and keep asyncio loop alive."""
    from finance_service.app import startup_orchestrator
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(startup_orchestrator())
        logger.info("✅ Orchestrator initialized")
        loop.run_forever()
    except Exception as e:
        logger.exception("Orchestrator crashed")
    finally:
        loop.close()

if __name__ == "__main__":
    logger.info("🚀 Starting finance service (simple Flask-main + asyncio daemon)")
    # Start orchestrator in a daemon thread
    orch_thread = threading.Thread(target=start_orchestrator, daemon=True)
    orch_thread.start()
    # Give it a moment to initialize
    import time; time.sleep(3)
    # Run Flask app in main thread
    from finance_service.app import app
    app.run(host='0.0.0.0', port=8801, debug=False, use_reloader=False, threaded=True)
