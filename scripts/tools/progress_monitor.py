#!/usr/bin/env python3
"""
Progress Monitor - Automated strategy performance check every 30 minutes.
Checks latest backtest results, compares to targets, and sends Telegram notifications.
"""

import sqlite3
import json
import os
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

WORKSPACE = Path("/home/eric/.openclaw/workspace/AITradeAgent")
DB_PATH = WORKSPACE / "finance_service" / "storage" / "backtest.sqlite"
PROGRESS_LOG = WORKSPACE / "memory" / "progress_monitor.md"
STATE_FILE = WORKSPACE / "memory" / "progress_monitor_state.json"

TARGET_CAGR = 20.0  # %
TARGET_SHARPE = 1.0
TARGET_MAX_DD = 30.0

def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {"last_backtest_id": None, "last_notified": None}

def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def get_latest_backtest():
    """Fetch most recent backtest run from database."""
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM backtest_runs 
        ORDER BY created_at DESC 
        LIMIT 1
    """)
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def analyze_performance(metrics):
    """Compare metrics to targets and provide recommendations."""
    cagr = metrics.get("cagr_pct", 0)
    sharpe = metrics.get("sharpe_ratio", 0)
    max_dd = metrics.get("max_drawdown_pct", 0)
    trades = metrics.get("total_trades", 0)

    status = []
    recommendations = []
    overall = ""

    if trades == 0:
        status.append("❌ NO TRADES - strategy is inactive")
        recommendations.append("CRITICAL: Relax entry filters (lower RSI threshold, remove SMA10, or add news sentiment)")
        overall = "❌ FAILED"
    else:
        if cagr >= TARGET_CAGR:
            status.append(f"✅ CAGR above target: {cagr:.1f}% >= {TARGET_CAGR}%")
        else:
            status.append(f"⚠️ CAGR below target: {cagr:.1f}% < {TARGET_CAGR}%")
            overall = "⚠️ UNDER TARGET" if not overall else overall
        
        if sharpe >= TARGET_SHARPE:
            status.append(f"✅ Sharpe acceptable: {sharpe:.2f} >= {TARGET_SHARPE}")
        else:
            status.append(f"⚠️ Sharpe low: {sharpe:.2f} < {TARGET_SHARPE}")
            recommendations.append("Improve risk-adjusted returns: add trend filter or increase take-profit ratios")
            overall = "⚠️ UNDER TARGET" if not overall else overall

        if max_dd > TARGET_MAX_DD:
            status.append(f"❌ Drawdown excessive: {max_dd:.1f}% > {TARGET_MAX_DD}%")
            recommendations.append("Reduce position size or add stop-loss tightening")
            overall = "❌ FAILED" if not overall else overall
        else:
            status.append(f"✅ Drawdown within limit: {max_dd:.1f}%")
        
        if overall == "" and cagr >= TARGET_CAGR and sharpe >= TARGET_SHARPE and max_dd <= TARGET_MAX_DD:
            overall = "✅ ON TARGET"

    return {
        "status": status,
        "recommendations": recommendations,
        "metrics": metrics,
        "overall": overall
    }

def log_progress(analysis):
    """Append analysis to progress log and write latest summary to file."""
    PROGRESS_LOG.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(PROGRESS_LOG, "a") as f:
        f.write(f"\n## {timestamp}\n\n")
        f.write("### Latest Backtest Results\n")
        f.write(json.dumps(analysis["metrics"], indent=2) + "\n\n")
        f.write("### Assessment\n")
        for s in analysis["status"]:
            f.write(f"- {s}\n")
        if analysis["recommendations"]:
            f.write("\n### Recommended Actions\n")
            for r in analysis["recommendations"]:
                f.write(f"- {r}\n")
        f.write("\n---\n")
    
    # Also write latest summary to a simple file for quick reading
    latest_summary = f"""
📊 AiTradeAgent Progress Report ({timestamp})
Strategy: {analysis['metrics'].get('strategy', 'Unknown')}
Period: {analysis['metrics'].get('start_date', 'N/A')} to {analysis['metrics'].get('end_date', 'N/A')}
Symbols: {analysis['metrics'].get('symbols_count', 'N/A')}

CAGR: {analysis['metrics'].get('cagr_pct', 0):.2f}%
Sharpe: {analysis['metrics'].get('sharpe_ratio', 0):.2f}
Max DD: {analysis['metrics'].get('max_drawdown_pct', 0):.2f}%
Trades: {analysis['metrics'].get('total_trades', 0):,}
Final Value: ${analysis['metrics'].get('final_value', 0):,.2f}

Overall: {analysis['overall']}

Assessment:
""".strip() + "\n" + "\n".join(analysis["status"])
    if analysis["recommendations"]:
        latest_summary += "\n\nRecommended Actions:\n" + "\n".join(f"  • {r}" for r in analysis["recommendations"])
    
    with open(WORKSPACE / "memory" / "latest_progress.txt", "w") as f:
        f.write(latest_summary)

def send_telegram(message: str):
    """Send notification via direct Telegram HTTP API.
    Note: market-hours scheduling is handled by progress_monitor_daemon.py.
    """
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not bot_token or not chat_id:
        # Try loading from .env file directly
        env_file = WORKSPACE / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("TELEGRAM_BOT_TOKEN="):
                    bot_token = line.split("=", 1)[1].strip()
                elif line.startswith("TELEGRAM_CHAT_ID="):
                    chat_id = line.split("=", 1)[1].strip()
    if not bot_token or not chat_id:
        print("❌ TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set")
        return False
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown",
            "disable_web_page_preview": "true",
        }).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.getcode() == 200:
                print("✅ Telegram notification sent via direct API")
                return True
            else:
                print(f"❌ Telegram API error: HTTP {resp.getcode()}")
                return False
    except Exception as e:
        print(f"❌ Failed to send Telegram: {e}")
        return False

def main():
    state = load_state()
    latest = get_latest_backtest()
    
    if not latest:
        msg = "❌ No backtest data found. Run initial backtest first."
        print(msg)
        log_progress({"status": ["No backtest data"], "recommendations": ["Run backtest with current strategy"], "metrics": {}})
        # Send notification only if we haven't sent recently
        now = datetime.now()
        last_notified = state.get("last_notified")
        if not last_notified or (now - datetime.fromisoformat(last_notified)).total_seconds() > 1800:
            send_telegram(msg + "\n\nBlocking: No backtest data available.")
            state["last_notified"] = now.isoformat()
            save_state(state)
        return
    
    current_run_id = latest['id']
    last_run_id = state.get("last_backtest_id")
    
    metrics = {
        "total_return_pct": latest["total_return_pct"],
        "cagr_pct": latest["cagr_pct"],
        "sharpe_ratio": latest["sharpe_ratio"],
        "max_drawdown_pct": latest["max_drawdown_pct"],
        "total_trades": latest["total_trades"],
        "final_value": latest["final_equity"],
        "run_date": latest.get("created_at") or f"{latest['start_date']} to {latest['end_date']}",
        "start_date": latest["start_date"],
        "end_date": latest["end_date"],
        "symbols_count": len(latest.get("symbols", [])) if isinstance(latest.get("symbols"), list) else 20,
        "strategy": latest.get("run_name", "Unknown")
    }
    
    analysis = analyze_performance(metrics)
    
    # Build notification message
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    msg_lines = [
        f"📊 *AiTradeAgent Progress Report* ({now_str})",
        f"Strategy: {metrics['strategy']}",
        f"Period: {latest['start_date'][:10]} to {latest['end_date'][:10]}",
        f"Symbols: {metrics['symbols_count']}",
        "",
        f"*CAGR:* {metrics['cagr_pct']:.2f}% {'✅' if metrics['cagr_pct'] >= TARGET_CAGR else '⚠️'}",
        f"*Sharpe:* {metrics['sharpe_ratio']:.2f} {'✅' if metrics['sharpe_ratio'] >= TARGET_SHARPE else '⚠️'}",
        f"*Max DD:* {metrics['max_drawdown_pct']:.2f}% {'✅' if metrics['max_drawdown_pct'] <= TARGET_MAX_DD else '❌'}",
        f"*Trades:* {metrics['total_trades']:,}",
        f"*Final Value:* ${metrics['final_value']:,.2f}",
        "",
        f"*Overall:* {analysis['overall']}",
        "",
        "Assessment:"
    ]
    msg_lines.extend(analysis["status"])
    
    if analysis["recommendations"]:
        msg_lines.append("")
        msg_lines.append("🔧 Recommended Actions:")
        for r in analysis["recommendations"]:
            msg_lines.append(f"  • {r}")
    
    # Check if there's a new backtest or if we've been stuck
    blocking_info = ""
    if current_run_id == last_run_id:
        # No new backtest since last notification
        last_notified_str = state.get("last_notified", "never")
        if last_notified_str:
            last_notified_dt = datetime.fromisoformat(last_notified_str)
            hours_since = (datetime.now() - last_notified_dt).total_seconds() / 3600
            if hours_since >= 2:
                blocking_info = f"\n\n⏳ *Blocking:* No new backtest completed in {hours_since:.1f} hours. The strategy may need adjustment or backtest is stuck."
        else:
            blocking_info = "\n\n⏳ *Blocking:* This is the first notification."
    else:
        # New backtest completed
        blocking_info = f"\n\n🆕 *New backtest result detected!* Run ID: {current_run_id}"
    
    full_message = "\n".join(msg_lines) + blocking_info
    
    # Send notification if:
    # 1. New backtest results (current_run_id != last_run_id)
    # 2. Or we haven't notified in the last 30 minutes (to avoid spam if same result)
    should_notify = False
    if current_run_id != last_run_id:
        should_notify = True
    else:
        last_notified = state.get("last_notified")
        if last_notified:
            time_diff = (datetime.now() - datetime.fromisoformat(last_notified)).total_seconds()
            if time_diff > 1800:  # 30 minutes
                should_notify = True
        else:
            should_notify = True
    
    if should_notify:
        send_telegram(full_message)
        state["last_backtest_id"] = current_run_id
        state["last_notified"] = datetime.now().isoformat()
        save_state(state)
    
    log_progress(analysis)
    
    # Print to console as well
    print(full_message)

if __name__ == "__main__":
    main()
