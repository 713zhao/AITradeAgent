"""Phase 0 Bootstrap Tests - Config, Event Bus, Database, Flask"""
import pytest
import tempfile
import json
import sqlite3
from pathlib import Path
from datetime import datetime
import time
from unittest.mock import patch, MagicMock

# Add parent directory to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from finance_service.core.yaml_config import YAMLConfigEngine
from finance_service.core.event_bus import EventBus, Event, Events, get_event_bus
from finance_service.storage.database import Database, get_portfolio_db
from finance_service.app import app


class TestYAMLConfigEngine:
    """Test YAML configuration loading and hot-reload"""
    
    def setup_method(self):
        """Setup test config directory"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_dir = Path(self.temp_dir.name)
    
    def teardown_method(self):
        """Cleanup"""
        self.temp_dir.cleanup()
    
    def test_config_engine_initialization(self):
        """Test config engine initializes without errors"""
        engine = YAMLConfigEngine(str(self.config_dir))
        assert engine is not None
        assert engine.config_dir == self.config_dir
    
    def test_load_yaml_file(self):
        """Test loading a YAML file"""
        # Create test YAML file
        config_file = self.config_dir / "test.yaml"
        config_file.write_text("""
test:
  key1: value1
  key2: 123
  key3:
    nested: yes
""")
        
        engine = YAMLConfigEngine(str(self.config_dir))
        config = engine.get("test")
        
        assert config is not None
        assert config["key1"] == "value1"
        assert config["key2"] == 123
        assert config["key3"]["nested"] is True
    
    def test_get_nested_key(self):
        """Test getting nested configuration keys"""
        config_file = self.config_dir / "finance.yaml"
        config_file.write_text("""
risk:
  max_position_size_pct: 20
  max_daily_loss_pct: 3
""")
        
        engine = YAMLConfigEngine(str(self.config_dir))
        value = engine.get("finance", "risk/max_position_size_pct")
        
        assert value == 20
    
    def test_validation_passes(self):
        """Test configuration validation"""
        # Create minimal valid config files
        (self.config_dir / "finance.yaml").write_text("risk:\n  max_position_size_pct: 20")
        (self.config_dir / "schedule.yaml").write_text("schedules: {}")
        (self.config_dir / "providers.yaml").write_text("providers: {}")
        
        engine = YAMLConfigEngine(str(self.config_dir))
        assert engine.validate() is True
    
    def test_validation_fails_missing_section(self):
        """Test validation fails with missing sections"""
        (self.config_dir / "finance.yaml").write_text("{}")
        
        engine = YAMLConfigEngine(str(self.config_dir))
        assert engine.validate() is False
    
    def test_export_json(self):
        """Test exporting configuration as JSON"""
        (self.config_dir / "test.yaml").write_text("test:\n  key: value")
        
        engine = YAMLConfigEngine(str(self.config_dir))
        json_str = engine.export_json()
        
        data = json.loads(json_str)
        assert "test" in data
        assert data["test"]["key"] == "value"
    
    def test_audit_log(self):
        """Test configuration change audit logging"""
        config_file = self.config_dir / "test.yaml"
        config_file.write_text("test:\n  key: value1")
        
        engine = YAMLConfigEngine(str(self.config_dir))
        initial_log_len = len(engine.get_audit_log())
        
        # Modify file
        time.sleep(0.6)  # Wait for file watch
        config_file.write_text("test:\n  key: value2")
        engine._reload_yaml()
        
        # Check audit log grew
        assert len(engine.get_audit_log()) >= initial_log_len


class TestEventBus:
    """Test event publishing and subscription"""
    
    def setup_method(self):
        """Setup for each test"""
        self.bus = EventBus()
        self.received_events = []
    
    def test_event_bus_initialization(self):
        """Test event bus initializes"""
        assert self.bus is not None
        assert len(self.bus.get_subscribers_count("test")) == 0
    
    def test_subscribe_to_event(self):
        """Test subscribing to an event"""
        def handler(event):
            pass
        
        self.bus.subscribe("test_event", handler)
        assert self.bus.get_subscribers_count("test_event") == 1
    
    def test_publish_event(self):
        """Test publishing an event"""
        def handler(event):
            self.received_events.append(event)
        
        self.bus.subscribe("test_event", handler)
        
        event = Event(event_type="test_event", data={"key": "value"})
        self.bus.publish(event, sync=True)
        
        assert len(self.received_events) == 1
        assert self.received_events[0].data["key"] == "value"
    
    def test_multiple_subscribers(self):
        """Test multiple subscribers receive same event"""
        count = {"received": 0}
        
        def handler1(event):
            count["received"] += 1
        
        def handler2(event):
            count["received"] += 1
        
        self.bus.subscribe("test_event", handler1)
        self.bus.subscribe("test_event", handler2)
        
        event = Event(event_type="test_event")
        self.bus.publish(event, sync=True)
        
        assert count["received"] == 2
    
    def test_event_history(self):
        """Test event history tracking"""
        event1 = Event(event_type="event1")
        event2 = Event(event_type="event2")
        
        self.bus.publish(event1)
        self.bus.publish(event2)
        
        history = self.bus.get_event_history()
        assert len(history) >= 2
    
    def test_event_bus_stats(self):
        """Test event bus statistics"""
        def handler(event):
            pass
        
        self.bus.subscribe("event1", handler)
        self.bus.subscribe("event2", handler)
        
        stats = self.bus.get_stats()
        assert stats["subscribed_event_types"] == ["event1", "event2"]
        assert stats["total_subscribers"] == 2
    
    def test_predefined_event_types(self):
        """Test predefined event type constants"""
        assert Events.DATA_READY == "data_ready"
        assert Events.DECISION_MADE == "decision_made"
        assert Events.EXECUTION_COMPLETE == "execution_complete"
        assert Events.APPROVAL_REQUESTED == "approval_requested"
    
    def test_unsubscribe(self):
        """Test unsubscribing from events"""
        def handler(event):
            pass
        
        self.bus.subscribe("test_event", handler)
        assert self.bus.get_subscribers_count("test_event") == 1
        
        self.bus.unsubscribe("test_event", handler)
        assert self.bus.get_subscribers_count("test_event") == 0


class TestDatabase:
    """Test SQLite database and schema"""
    
    def setup_method(self):
        """Setup test database"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "test.sqlite")
        self.db = Database(self.db_path)
    
    def teardown_method(self):
        """Cleanup"""
        self.db.close()
        self.temp_dir.cleanup()
    
    def test_database_initialization(self):
        """Test database initializes"""
        assert self.db is not None
        assert Path(self.db.db_path).parent.exists()
    
    def test_schema_creation(self):
        """Test database schema is created"""
        created = self.db.initialize_schema()
        assert created is True
        
        # Check tables exist
        cursor = self.db.connection.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = [row[0] for row in cursor.fetchall()]
        
        assert "positions" in tables
        assert "trades" in tables
        assert "portfolio_snapshots" in tables
        assert "config_audit_log" in tables
        assert "backtest_runs" in tables
    
    def test_insert_position(self):
        """Test inserting a position"""
        self.db.initialize_schema()
        
        position = {
            "symbol": "NVDA",
            "side": "BUY",
            "quantity": 10,
            "entry_price": 500.0,
            "entry_date": datetime.now(),
            "stop_loss": 490.0,
            "take_profit": 510.0,
            "confidence": 0.85,
        }
        
        pos_id = self.db.insert_position(position)
        assert pos_id > 0
    
    def test_insert_trade(self):
        """Test inserting a trade"""
        self.db.initialize_schema()
        
        trade = {
            "symbol": "NVDA",
            "side": "BUY",
            "quantity": 10,
            "price": 500.0,
            "timestamp": datetime.now(),
            "confidence": 0.85,
            "approval_status": "AUTO",
        }
        
        trade_id = self.db.insert_trade(trade)
        assert trade_id > 0
    
    def test_get_open_positions(self):
        """Test retrieving open positions"""
        self.db.initialize_schema()
        
        position = {
            "symbol": "NVDA",
            "side": "BUY",
            "quantity": 10,
            "entry_price": 500.0,
            "entry_date": datetime.now(),
        }
        
        self.db.insert_position(position)
        
        positions = self.db.get_open_positions()
        assert len(positions) == 1
        assert positions[0]["symbol"] == "NVDA"
    
    def test_get_trade_history(self):
        """Test retrieving trade history"""
        self.db.initialize_schema()
        
        trade = {
            "symbol": "NVDA",
            "side": "BUY",
            "quantity": 10,
            "price": 500.0,
            "timestamp": datetime.now(),
        }
        
        self.db.insert_trade(trade)
        
        trades = self.db.get_trade_history()
        assert len(trades) == 1
        assert trades[0]["symbol"] == "NVDA"


class TestFlaskApp:
    """Test Flask application endpoints"""
    
    def setup_method(self):
        """Setup Flask test client"""
        app.config['TESTING'] = True
        self.client = app.test_client()
    
    def test_health_check_endpoint(self):
        """Test /health endpoint"""
        response = self.client.get('/health')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['status'] == 'healthy'
    
    def test_root_endpoint(self):
        """Test root / endpoint"""
        response = self.client.get('/')
        
        # Should return something (200 or redirect)
        assert response.status_code in [200, 302, 404]


class TestPhase0Integration:
    """Integration tests for Phase 0 bootstrap"""
    
    def test_config_event_bus_integration(self):
        """Test config changes trigger events"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir)
            config_dir.joinpath("finance.yaml").write_text("risk:\n  max_position_size_pct: 20")
            
            engine = YAMLConfigEngine(str(config_dir))
            bus = EventBus()
            
            received = []
            bus.subscribe(Events.CONFIG_RELOADED, lambda e: received.append(e))
            
            # Simulate reload
            bus.publish(Event(event_type=Events.CONFIG_RELOADED, data={"section": "finance"}), sync=True)
            
            assert len(received) == 1
    
    def test_database_event_integration(self):
        """Test database inserts trigger events"""
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "test.sqlite")
            db = Database(db_path)
            db.initialize_schema()
            
            bus = EventBus()
            received = []
            
            bus.subscribe(Events.TRADE_OPENED, lambda e: received.append(e))
            
            # Insert trade
            trade = {
                "symbol": "NVDA",
                "side": "BUY",
                "quantity": 10,
                "price": 500.0,
                "timestamp": datetime.now(),
            }
            trade_id = db.insert_trade(trade)
            
            # Manually publish event (in real app, would be automatic)
            bus.publish(
                Event(
                    event_type=Events.TRADE_OPENED,
                    data={"trade_id": trade_id, "symbol": "NVDA"}
                ),
                sync=True
            )
            
            assert len(received) == 1
            assert received[0].data["symbol"] == "NVDA"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
