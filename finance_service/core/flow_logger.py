"""Agent flow debug logger.

Enable with: AGENT_DEBUG=1

Usage:
    from finance_service.core.flow_logger import configure, flow

    configure()                               # startup, reads AGENT_DEBUG env var
    flow("MarketScanner", "START", "...")     # inside agents
    flow("MarketScanner", "DONE",  "...")
"""

import logging
import os

_flow_logger = logging.getLogger("agent.flow")
_configured = False

_ICONS = {
    "START":  "▶",
    "DONE":   "✓",
    "SKIP":   "⏭",
    "WARN":   "⚠",
    "ERROR":  "✗",
    "UPDATE": "⟳",
    "CHECK":  "🔍",
    "ALERT":  "🚨",
}


def _is_enabled() -> bool:
    return os.environ.get("AGENT_DEBUG", "0").strip().lower() in ("1", "true", "yes")


def configure(verbose: bool = False) -> None:
    """Call once at startup.  Activates flow logging when AGENT_DEBUG=1 or verbose=True."""
    global _configured
    if _configured:
        return
    _configured = True

    if not (_is_enabled() or verbose):
        return

    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s  %(message)s", datefmt="%H:%M:%S")
    )
    _flow_logger.addHandler(handler)
    _flow_logger.setLevel(logging.DEBUG)
    _flow_logger.propagate = False
    _flow_logger.info("[FLOW] ▶ Agent flow debug logging ENABLED (AGENT_DEBUG=1)")


def flow(agent: str, status: str, msg: str) -> None:
    """Emit one [FLOW] trace line.  No-op when AGENT_DEBUG is not set."""
    if not (_is_enabled() or _flow_logger.handlers):
        return
    icon = _ICONS.get(status.upper(), "•")
    _flow_logger.info("[FLOW] %s %-20s %-7s %s", icon, agent, status, msg)
