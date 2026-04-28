#!/usr/bin/env python3
"""
Telegram Notifier Agent - Watches memory/latest_progress.txt and sends Telegram via OpenClaw message tool.
Runs as a persistent subagent.
"""
import asyncio
from pathlib import Path
from datetime import datetime

WORKSPACE = Path("/home/eric/.openclaw/workspace/AITradeAgent")
SUMMARY_FILE = WORKSPACE / "memory" / "latest_progress.txt"
STATE_FILE = WORKSPACE / "memory" / "telegram_notifier_state.json"

# Try to import OpenClaw's message tool
try:
    from openclaw import message
except ImportError:
    print("Warning: openclaw message tool not importable, will use CLI fallback")
    message = None

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
        return None, None
    with open(SUMMARY_FILE) as f:
        content = f.read()
    mtime = datetime.fromtimestamp(SUMMARY_FILE.stat().st_mtime)
    return content, mtime

def save_state():
    state["last_sent"] = datetime.now().isoformat()
    with open(STATE_FILE, "w") as f:
        import json
        json.dump(state, f)

async def main():
    print("Telegram Notifier Agent started")
    while True:
        try:
            summary, mtime = load_summary()
            if summary and mtime and mtime > last_sent:
                # Send via OpenClaw message tool or CLI fallback
                sent = False
                if message:
                    try:
                        # Use the tool directly
                        await message.send(to='telegram:8383381149', message=summary)
                        print(f"[{datetime.now()}] Sent progress update via tool")
                        sent = True
                    except Exception as e:
                        print(f"[{datetime.now()}] Tool send failed: {e}")
                if not sent:
                    # CLI fallback with absolute path
                    import subprocess
                    OPENCLAW_CLI = "/home/eric/.npm-global/bin/openclaw"
                    try:
                        result = subprocess.run(
                            [OPENCLAW_CLI, 'message', 'send', '-t', '8383381149', '-m', summary],
                            capture_output=True,
                            text=True,
                            timeout=120
                        )
                        if result.returncode == 0:
                            print(f"[{datetime.now()}] Sent progress update via CLI")
                            sent = True
                        else:
                            print(f"[{datetime.now()}] CLI error: {result.stderr}")
                    except subprocess.TimeoutExpired:
                        print(f"[{datetime.now()}] CLI timeout")
                    except Exception as e:
                        print(f"[{datetime.now()}] CLI exception: {e}")
                if sent:
                    last_sent = mtime
                    save_state()
            await asyncio.sleep(60)  # check every minute
        except Exception as e:
            print(f"[{datetime.now()}] Loop error: {e}")
            await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(main())
