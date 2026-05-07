import re
with open("finance_service/agents/health_agent.py", "r") as f:
    text = f.read()

old_status = """        status = result.get("status", "??")
        
        # Get current portfolio info for context (with timeout to avoid blocking)"""
new_status = """        status = result.get("status", "??")
        reason = result.get("reason", "")
        realized_pnl = result.get("realized_pnl", 0.0)
        pnl_pct = result.get("pnl_pct", 0.0)
        hold_days = result.get("hold_days", 0)
        
        # Get current portfolio info for context (with timeout to avoid blocking)"""
text = text.replace(old_status, new_status)

old_msg = """        message += f"• Quantity: {quantity}\n"
        message += f"• Price: ${price:,.2f}\n"
        message += f"• Status: {status}\n"
        message += f"\n{portfolio_summary}" """

new_msg = """        message += f"• Quantity: {quantity}\n"
        message += f"• Price: ${price:,.2f}\n"
        
        if action.upper() == "SELL":
            pnl_sign = "+" if realized_pnl >= 0 else ""
            message += f"• Reason: {reason}\n"
            message += f"• P&L: {pnl_sign}${realized_pnl:,.2f} ({pnl_sign}{pnl_pct:.2f}%)\n"
            message += f"• Held for: {hold_days} days\n"
        
        message += f"• Status: {status}\n"
        message += f"\n{portfolio_summary}" """
text = text.replace(old_msg, new_msg)

with open("finance_service/agents/health_agent.py", "w") as f:
    f.write(text)

print("Patched health agent.")
