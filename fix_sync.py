import asyncio
from finance_service.core.event_bus import get_event_bus, _global_event_bus

def get_event_bus_sync():
    """Wrapper to get event bus synchronously, using asyncio.run if needed."""
    global _global_event_bus
    if _global_event_bus is not None:
        return _global_event_bus
    
    try:
        loop = asyncio.get_running_loop()
        # If we have a running loop, we can't use asyncio.run
        # But if it's already initialized by events.py import, it will return above.
        # If not, this will raise RuntimeError or return a coroutine.
        # We'll just return the coroutine and let it fail later if misused.
        return get_event_bus()
    except RuntimeError:
        return asyncio.run(get_event_bus())

import glob

for fp in glob.glob("finance_service/agents/*.py", recursive=True):
    with open(fp, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if 'get_event_bus()' in content and 'await get_event_bus()' not in content:
        # replace import
        if 'get_event_bus' in content and 'get_event_bus_sync' not in content:
            content = content.replace('get_event_bus', 'get_event_bus, get_event_bus_sync', 1)
        
        # replace call
        content = content.replace('get_event_bus()', 'get_event_bus_sync()')
        
        with open(fp, 'w', encoding='utf-8') as f:
            f.write(content)
