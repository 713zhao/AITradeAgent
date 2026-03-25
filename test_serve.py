#!/usr/bin/env python3
import asyncio, os, sys, traceback
os.chdir('/home/eric/.openclaw/workspace/AITradeAgent')
sys.path.insert(0, '.')

print("[1] About to import app...")
sys.stdout.flush()
from finance_service.app import app
print("[2] App imported")
sys.stdout.flush()

print("[3] Importing hypercorn...")
try:
    from hypercorn.config import Config
    from hypercorn.asyncio import serve
    print("[4] Hypercorn imported")
except Exception as e:
    print("Import hypercorn failed:", e)
    traceback.print_exc()
    sys.exit(1)

async def main():
    config = Config()
    config.bind = ["0.0.0.0:8801"]
    config.loglevel = "info"
    config.accesslog = "-"
    try:
        print("[5] Starting serve with timeout 2s...")
        await asyncio.wait_for(serve(app, config), timeout=2)
        print("Serve completed normally (unlikely)")
    except asyncio.TimeoutError:
        print("✅ Serve started and listening (timeout as expected)")
    except Exception as e:
        print(f"❌ Serve failed: {e}")
        traceback.print_exc()
        sys.exit(1)

print("[6] Running asyncio.run(main())...")
asyncio.run(main())
print("[7] asyncio.run returned")
