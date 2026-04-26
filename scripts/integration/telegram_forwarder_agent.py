#!/usr/bin/env python3
"""
Telegram Forwarder Agent - Watches progress file and sends updates via OpenClaw message.
Run this as a persistent subagent.
"""
import asyncio
import time
from pathlib import Path
from datetime import datetime

# In OpenClaw agent context, we have access to tools via imports?
# We'll use subprocess to call openclaw CLI, but that might hang.
# Alternatively, we can use the message tool directly if we are in an agent session.
# Since this will be spawned as a subagent, we can import the message tool from openclaw?
# Let's try to import the message module.

WORKSPACE = Path("/home/eric/.openclaw/workspace/AITradeAgent")
SUMMARY_FILE = WORKSPACE / "memory" / "latest_progress.txt"
STATE_FILE = WORKSPACE / "memory" / "telegram_forwarder_state.json"

# Load state
if STATE_FILE.exists():
    import json
    with open(STATE_FILE) as f:
        state = json.load(f)
    last_sent = datetime.fromisoformat(state.get("last_sent", "2000-01-01T00:00:00"))
else:
    last_sent = datetime(2000,1,1)
    state = {}

def load_summary():
    if not SUMMARY_FILE.exists():
        return None
    with open(SUMMARY_FILE) as f:
        return f.read()

def save_state():
    state["last_sent"] = datetime.now().isoformat()
    with open(STATE_FILE, "w") as f:
        import json
        json.dump(state, f)

async def main():
    print("Telegram forwarder agent started")
    while True:
        try:
            summary = load_summary()
            if summary:
                # Check if file is newer than last_sent
                mtime = datetime.fromtimestamp(SUMMARY_FILE.stat().st_mtime)
                if mtime > last_sent:
                    # Send via openclaw message CLI
                    import subprocess
                    try:
                        result = subprocess.run(
                            ['openclaw', 'message', 'send', '-t', '8383381149', '-m', summary],
                            capture_output=True,
                            text=True,
                            timeout=60
                        )
                        if result.returncode == 0:
                            print(f"Sent progress update at {datetime.now()}")
                            last_sent = mtime
                            save_state()
                        else:
                            print(f"CLI error: {result.stderr}")
                    except subprocess.TimeoutExpired:
                        print("CLI timeout, skipping this send")
                    except Exception as e:
                        print(f"Send failed: {e}")
            await asyncio.sleep(60)  # check every minute
        except Exception as e:
            print(f"Loop error: {e}")
            await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(main())
