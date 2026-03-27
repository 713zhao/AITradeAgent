#!/usr/bin/env python3
"""
PicotradeAgent Finance Service Launcher (Flask-threaded version)
Forces yfinance provider and runs Flask in a separate thread.
"""
import os
import sys
import asyncio
import threading
import time
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

def run_flask_app():
    """Run Flask app in a separate thread."""
    from finance_service.app import app
    # Turn off reloader; run in production-like mode
    try:
        logger.info("🔧 Flask thread: starting app.run()")
        app.run(host='0.0.0.0', port=8801, debug=False, use_reloader=False, threaded=True)
        logger.info("🔧 Flask thread: app.run() returned")
    except Exception as e:
        logger.exception(f"❌ Flask thread crashed: {e}")
        # Raising from thread won't stop main thread, but we log.

async def main():
    """Initialize orchestrator and keep the async event loop alive."""
    from finance_service.app import startup_orchestrator
    logger.info("🔧 Initializing orchestrator...")
    await startup_orchestrator()
    logger.info("✅ Orchestrator initialized. Service is now running.")
    logger.info("⏳ Entering indefinite wait loop.")
    try:
        await asyncio.Event().wait()
        logger.warning("⚠️ Event wait returned unexpectedly! This should never happen.")
    except asyncio.CancelledError:
        logger.warning("⏹ Async wait cancelled")
        raise
    except Exception as e:
        logger.error(f"❌ Event wait raised {type(e).__name__}: {e}")
        raise

def main_entry():
    """Entry point with auto-restart."""
    logger.info("🚀 Starting PicotradeAgent Finance Service (Flask-threaded mode)")
    logger.info("📊 Market data source: yfinance (free)")
    logger.info("💰 Trading mode: PAPER (simulated)")
    logger.info("🔌 Port: 8801")
    logger.info("🌐 Server: Flask (threaded)")
    logger.info("🔁 Auto-restart: enabled")

    restart_delay = 5
    while True:
        try:
            # Start Flask in a daemon thread
            flask_thread = threading.Thread(target=run_flask_app, daemon=True)
            flask_thread.start()
            logger.info("✅ Flask server thread started")

            # Run the orchestrator in the main thread
            try:
                asyncio.run(main())
            except SystemExit as e:
                logger.warning(f"🔄 SystemExit caught (code={e.code}). Restarting...")
                raise
            except KeyboardInterrupt:
                logger.info("🛑 Service stopped by user (KeyboardInterrupt)")
                sys.exit(0)
            except BaseException as e:
                logger.error(f"❌ Service main loop crashed with {type(e).__name__}: {e}", exc_info=True)
                raise
            # Should not get here unless main() returned
            logger.warning("⏹ Async main returned. Restarting...")
        except (SystemExit, KeyboardInterrupt):
            # User interrupt
            logger.info("🛑 Service stopping")
            sys.exit(0)
        except Exception as e:
            logger.error(f"❌ Service crashed: {type(e).__name__}: {e}. Restarting in {restart_delay}s...", exc_info=True)
            time.sleep(restart_delay)
        except BaseException as e:
            logger.error(f"❌ Unhandled BaseException: {type(e).__name__}: {e}. Restarting in {restart_delay}s...", exc_info=True)
            time.sleep(restart_delay)

if __name__ == "__main__":
    main_entry()
