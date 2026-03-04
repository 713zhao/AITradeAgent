"""YAML Configuration Engine with hot-reload support"""
import os
import yaml
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import threading
import time

logger = logging.getLogger(__name__)


class ConfigChangeHandler(FileSystemEventHandler):
    """Watches for changes in YAML config files"""
    
    def __init__(self, config_manager):
        self.config_manager = config_manager
    
    def on_modified(self, event):
        """Handle file modification"""
        if event.is_directory:
            return
        
        if event.src_path.endswith('.yaml') or event.src_path.endswith('.yml'):
            logger.info(f"Config file modified: {event.src_path}")
            # Small delay to ensure file write is complete
            time.sleep(0.5)
            self.config_manager._reload_yaml()


class YAMLConfigEngine:
    """Load and manage YAML configuration with hot-reload"""
    
    def __init__(self, config_dir: str = "config"):
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        # Configuration storage
        self._config: Dict[str, Any] = {}
        self._timestamps: Dict[str, float] = {}
        self._audit_log: list = []
        
        # Hot-reload
        self._observer: Optional[Observer] = None
        self._reload_lock = threading.Lock()
        
        # Initial load
        self._reload_yaml()
        
        logger.info(f"YAML Config Engine initialized (dir: {self.config_dir})")
    
    def _load_yaml_file(self, file_path: Path) -> Dict[str, Any]:
        """Load a single YAML file with error handling"""
        try:
            if not file_path.exists():
                logger.warning(f"Config file not found: {file_path}, using empty dict")
                return {}
            
            with open(file_path, 'r') as f:
                content = yaml.safe_load(f)
                return content if content else {}
        
        except yaml.YAMLError as e:
            logger.error(f"YAML parse error in {file_path}: {e}")
            return {}
        except Exception as e:
            logger.error(f"Error loading {file_path}: {e}")
            return {}
    
    def _reload_yaml(self):
        """Reload all YAML configuration files"""
        with self._reload_lock:
            old_config = self._config.copy()
            new_config: Dict[str, Any] = {}
            
            # Load all YAML files in config directory
            for yaml_file in sorted(self.config_dir.glob('*.yaml')):
                file_name = yaml_file.stem
                logger.debug(f"Loading config from {yaml_file.name}")
                
                # Load file
                content = self._load_yaml_file(yaml_file)
                if content:
                    new_config[file_name] = content
                    self._timestamps[file_name] = yaml_file.stat().st_mtime
            
            # Check for differences and log
            if old_config != new_config:
                self._log_config_change(old_config, new_config)
                self._config = new_config
                logger.info(f"Configuration reloaded at {datetime.now().isoformat()}")
            else:
                logger.debug("Configuration unchanged")
    
    def _log_config_change(self, old_config: Dict, new_config: Dict):
        """Log configuration changes to audit log"""
        audit_entry = {
            "timestamp": datetime.now().isoformat(),
            "action": "config_reload",
            "changes": self._get_config_diff(old_config, new_config)
        }
        self._audit_log.append(audit_entry)
        
        # Keep only last 100 entries
        if len(self._audit_log) > 100:
            self._audit_log = self._audit_log[-100:]
        
        for change in audit_entry["changes"]:
            logger.info(f"Config change: {change}")
    
    def _get_config_diff(self, old_config: Dict, new_config: Dict) -> list:
        """Calculate differences between old and new config"""
        changes = []
        
        # Check for modified or new keys
        for key in new_config:
            if key not in old_config:
                changes.append(f"Added section: {key}")
            elif old_config[key] != new_config[key]:
                changes.append(f"Modified section: {key}")
        
        # Check for removed keys
        for key in old_config:
            if key not in new_config:
                changes.append(f"Removed section: {key}")
        
        return changes
    
    def start_hot_reload(self):
        """Start watching for configuration changes"""
        if self._observer is not None:
            logger.warning("Hot-reload already running")
            return
        
        try:
            handler = ConfigChangeHandler(self)
            self._observer = Observer()
            self._observer.schedule(handler, str(self.config_dir), recursive=False)
            self._observer.start()
            logger.info("Configuration hot-reload started")
        except Exception as e:
            logger.error(f"Failed to start hot-reload: {e}")
    
    def stop_hot_reload(self):
        """Stop watching for configuration changes"""
        if self._observer is None:
            return
        
        try:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
            logger.info("Configuration hot-reload stopped")
        except Exception as e:
            logger.error(f"Error stopping hot-reload: {e}")
    
    def get(self, section: str, key: Optional[str] = None, default: Any = None) -> Any:
        """Get configuration value"""
        # Get section
        section_data = self._config.get(section, {})
        
        if key is None:
            return section_data if section_data else default
        
        # Navigate nested keys (e.g., "finance/risk/max_position_size_pct")
        keys = key.split("/")
        value = section_data
        
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        
        return value if value is not None else default
    
    def get_all(self) -> Dict[str, Any]:
        """Get all configuration"""
        return self._config.copy()
    
    def validate(self) -> bool:
        """Validate configuration"""
        errors = []
        
        # Check finance config
        finance = self._config.get('finance', {})
        if not finance:
            errors.append("Missing 'finance' configuration section")
        else:
            # Validate risk settings
            risk = finance.get('risk', {})
            if risk.get('max_position_size_pct', 0) <= 0:
                errors.append("risk.max_position_size_pct must be > 0")
            if risk.get('max_exposure_pct', 0) <= 0:
                errors.append("risk.max_exposure_pct must be > 0")
        
        # Check schedule config
        schedule = self._config.get('schedule', {})
        if not schedule:
            errors.append("Missing 'schedule' configuration section")
        
        # Check providers config
        providers = self._config.get('providers', {})
        if not providers:
            errors.append("Missing 'providers' configuration section")
        
        if errors:
            for error in errors:
                logger.error(f"Config validation error: {error}")
            return False
        
        logger.info("Configuration validation passed")
        return True
    
    def get_audit_log(self) -> list:
        """Get configuration change audit log"""
        return self._audit_log.copy()
    
    def export_json(self, file_path: Optional[str] = None) -> str:
        """Export current configuration as JSON"""
        config_json = json.dumps(self._config, indent=2, default=str)
        
        if file_path:
            Path(file_path).parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, 'w') as f:
                f.write(config_json)
            logger.info(f"Configuration exported to {file_path}")
        
        return config_json
    
    def __repr__(self) -> str:
        sections = list(self._config.keys())
        return f"YAMLConfigEngine(sections={sections}, dir={self.config_dir})"
