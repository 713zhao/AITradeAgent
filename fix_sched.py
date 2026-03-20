import os
filepath = 'finance_service/agents/scheduler_agent.py'
with open(filepath, 'r') as f:
    content = f.read()

content = content.replace('\\"', '"')
content = content.replace("\\'", "'")

with open(filepath, 'w') as f:
    f.write(content)
