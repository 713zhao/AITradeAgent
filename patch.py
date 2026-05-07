import re
with open("finance_service/agents/execution_agent.py", "r") as f:
    t = f.read()
t = t.replace(
    '"timestamp": datetime.utcnow().isoformat(),\n                }',
    '"timestamp": datetime.utcnow().isoformat(),\n                    "reason": trade_proposal.rationale[0] if trade_proposal.rationale else "Strategy execution",\n                }'
)
with open("finance_service/agents/execution_agent.py", "w") as f:
    f.write(t)
