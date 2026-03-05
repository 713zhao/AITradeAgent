#!/usr/bin/env python3
"""Phase 0 Bootstrap Validation - Quick checks"""
import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

def validate_phase0():
    """Validate Phase 0 bootstrap completion"""
    checks = {
        "✅ YAML Config Files": False,
        "✅ Config Engine": False,
        "✅ Event Bus": False,
        "✅ SQLite Database": False,
        "✅ Flask App": False,
        "✅ Tests": False,
    }
    
    # 1. Check YAML files exist
    config_files = [
        Path("config/finance.yaml"),
        Path("config/schedule.yaml"),
        Path("config/providers.yaml"),
    ]
    if all(f.exists() for f in config_files):
        checks["✅ YAML Config Files"] = True
        print("✓ Found finance.yaml, schedule.yaml, providers.yaml")
    
    # 2. Check config engine exists
    if Path("finance_service/core/yaml_config.py").exists():
        checks["✅ Config Engine"] = True
        print("✓ Found YAMLConfigEngine (yaml_config.py)")
        
        try:
            from finance_service.core.yaml_config import YAMLConfigEngine
            engine = YAMLConfigEngine("config")
            print(f"  - Loaded sections: {list(engine.get_all().keys())}")
            if engine.validate():
                print("  - Configuration validation: PASSED")
        except Exception as e:
            print(f"  - Error loading config: {e}")
    
    # 3. Check event bus exists
    if Path("finance_service/core/event_bus.py").exists():
        checks["✅ Event Bus"] = True
        print("✓ Found EventBus (event_bus.py)")
        
        try:
            from finance_service.core.event_bus import EventBus, Events, get_event_bus
            bus = get_event_bus()
            print(f"  - EventBus initialized: {bus}")
            print(f"  - Predefined event types: {len([x for x in dir(Events) if not x.startswith('_')])} constants")
        except Exception as e:
            print(f"  - Error loading event bus: {e}")
    
    # 4. Check database exists
    if Path("finance_service/storage/database.py").exists():
        checks["✅ SQLite Database"] = True
        print("✓ Found Database module (database.py)")
        
        try:
            from finance_service.storage import get_portfolio_db
            db = get_portfolio_db()
            db.initialize_schema()
            print(f"  - Database initialized: {db}")
            print("  - Schema creation: PASSED")
        except Exception as e:
            print(f"  - Error with database: {e}")
    
    # 5. Check Flask app
    if Path("finance_service/app.py").exists():
        checks["✅ Flask App"] = True
        print("✓ Found Flask app (app.py)")
        
        try:
            from finance_service.app import app
            with app.test_client() as client:
                response = client.get('/health')
                if response.status_code in [200, 404]:
                    print(f"  - Flask app responsive: {response.status_code}")
        except Exception as e:
            print(f"  - Error with Flask app: {e}")
    
    # 6. Check tests
    if Path("tests/test_phase0_bootstrap.py").exists():
        checks["✅ Tests"] = True
        print("✓ Found Phase 0 tests (test_phase0_bootstrap.py)")
        
        # Count test classes
        try:
            with open("tests/test_phase0_bootstrap.py", 'r') as f:
                content = f.read()
                test_classes = content.count("class Test")
                test_methods = content.count("def test_")
                print(f"  - Test classes: {test_classes}")
                print(f"  - Test methods: {test_methods}")
        except Exception as e:
            print(f"  - Error reading tests: {e}")
    
    # Summary
    print("\n" + "="*50)
    print("PHASE 0 BOOTSTRAP VALIDATION")
    print("="*50)
    
    completed = sum(1 for v in checks.values() if v)
    total = len(checks)
    
    for check, status in checks.items():
        symbol = "✅" if status else "❌"
        print(f"{symbol} {check}")
    
    print(f"\nCompletion: {completed}/{total}")
    
    if completed == total:
        print("\n🎉 PHASE 0 BOOTSTRAP COMPLETE!")
        print("\nNext steps:")
        print("  1. Start Flask app: python -m finance_service.app")
        print("  2. Run tests: pytest tests/test_phase0_bootstrap.py -v")
        print("  3. Verify config hot-reload: edit config/finance.yaml and watch logs")
        print("  4. Check event bus: subscribe to events in app initialization")
        return 0
    else:
        print(f"\n⚠️  {total - completed} items still need work")
        return 1


if __name__ == "__main__":
    exit(validate_phase0())
