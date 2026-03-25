#!/usr/bin/env python3
import asyncio
import os, sys
os.chdir('/home/eric/.openclaw/workspace/AITradeAgent')
sys.path.insert(0, '.')

try:
    from finance_service.app import startup_orchestrator
    print("Imported startup_orchestrator OK")
    async def main():
        orch = await startup_orchestrator()
        print(f"STARTUP COMPLETE, orchestrator id: {id(orch)}")
        # Keep running for a few seconds to allow any background tasks
        await asyncio.sleep(3)
        print("MAIN DONE")
    asyncio.run(main())
except Exception as e:
    import traceback
    print("FAILED")
    traceback.print_exc()
    sys.exit(1)
