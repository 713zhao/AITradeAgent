import glob

for fp in glob.glob("finance_service/**/*.py", recursive=True):
    with open(fp, 'r') as f:
        content = f.read()
    if 'from finance_service.core.events import Event, Events, get_event_bus' in content:
        content = content.replace('from finance_service.core.events import Event, Events, get_event_bus', 'from finance_service.core.event_bus import Event, Events, get_event_bus')
        with open(fp, 'w') as f:
            f.write(content)
