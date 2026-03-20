import os

def fix_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()
    
    content = content.replace('\\\\"', '"')
    content = content.replace("\\\\'", "'")
    
    with open(filepath, 'w') as f:
        f.write(content)

fix_file('finance_service/core/event_bus.py')
fix_file('finance_service/agents/scheduler_agent.py')
