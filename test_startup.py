#!/usr/bin/env python3
import asyncio
import sys
import os

# Ensure we're in the right directory
os.chdir('/home/eric/.openclaw/workspace/AITradeAgent')
sys.path.insert(0, '.')

try:
    from finance_service.app import startup_orchestrator
    print("Imported startup_orchestrator OK")
    result = asyncio.run(startup_orchestrator())
    print(f"STARTUP COMPLETE, orchestrator id: {id(result)}")
except Exception as e:
    import traceback
    print("STARTUP FAILED")
    traceback.print_exc()
    sys.exit(1)
