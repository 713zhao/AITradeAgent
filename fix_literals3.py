import re

def clean(fp):
    with open(fp, 'r') as f:
        s = f.read()
    s = re.sub(r'\\"', '"', s)
    with open(fp, 'w') as f:
        f.write(s)

clean('finance_service/core/event_bus.py')
clean('finance_service/agents/scheduler_agent.py')
