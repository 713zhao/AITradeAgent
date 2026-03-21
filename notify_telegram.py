#!/usr/bin/env python3
"""Read latest progress summary and send via Telegram."""
import sys
from pathlib import Path

WORKSPACE = Path("/home/eric/.openclaw/workspace/AITradeAgent")
SUMMARY_FILE = WORKSPACE / "memory" / "latest_progress.txt"

if not SUMMARY_FILE.exists():
    print("No progress summary found")
    sys.exit(1)

with open(SUMMARY_FILE, "r") as f:
    message = f.read()

# Try to send via openclaw CLI
import subprocess
try:
    result = subprocess.run(
        ['openclaw', 'message', 'send', '-t', '8383381149', '-m', message],
        capture_output=True,
        text=True,
        timeout=60
    )
    if result.returncode == 0:
        print("Telegram notification sent")
        sys.exit(0)
    else:
        print(f"CLI error: {result.stderr}")
except subprocess.TimeoutExpired:
    print("CLI timed out")
except Exception as e:
    print(f"Exception: {e}")

# Fallback: print to stdout for cron log
print("\n" + "="*60)
print("TELEGRAM NOTIFICATION (copy manually):")
print("="*60)
print(message)
print("="*60)
