"""YAML-based configuration management.

Reads configuration from config/config.yaml with hot-reload support.
Provides hierarchical get() with defaults.
"""
import os
import yaml
import logging
from typing import Any, Dict, Optional, List
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import threading

logger = logging.getLogger(__name__)


class ConfigChangeHandler(FileSystemEventHandler):
    """Watchdog handler for config file changes"""

    def __init__(self, callback):
        self.callback = callback

    def on_modified(self, event):
        if not event.is_directory and event.src_path.endswith(('.yaml', '.yml')):
            logger.info(f"Config file changed: {event.src_path}")
            self.callback()


class YAMLConfigEngine:
    """Central configuration from YAML with optional hot-reload"""

    def __init__(self, config_dir: str = "config", enable_watchdog: bool = False):
        self.config_dir = Path(config_dir).resolve()
        self.config_file = self.config_dir / "config.yaml"
        self._config: Dict[str, Any] = {}
        self._observer: Optional[Observer] = None
        self._reload_callback = None
        self.load()

        if enable_watchdog:
            self.start_watchdog()

    def load(self):
        """Load config from YAML file"""
        if not self.config_file.exists():
            logger.warning(f"Config file not found: {self.config_file}. Using defaults.")
            self._config = {}
            return

        try:
            with open(self.config_file, 'r') as f:
                self._config = yaml.safe_load(f) or {}
            logger.info(f"Loaded config from {self.config_file}")
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            self._config = {}

    def get(self, section: str, key: str, default: Any = None) -> Any:
        """Get config value with dot-notation support

        Example: get("finance", "risk/max_position_size_pct", default=10)
        """
        if not section:
            return default

        section_dict = self._config.get(section, {})
        if not isinstance(section_dict, dict):
            return default

        # Support nested keys with /
        parts = key.split('/')
        value = section_dict
        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return default
        return value

    def get_section(self, section: str) -> Dict[str, Any]:
        """Get entire section as dict"""
        return self._config.get(section, {}).copy()

    def set(self, section: str, key: str, value: Any, persist: bool = True):
        """Set config value (optional persistence)"""
        if section not in self._config:
            self._config[section] = {}
        
        parts = key.split('/')
        d = self._config[section]
        for part in parts[:-1]:
            if part not in d:
                d[part] = {}
            d = d[part]
        d[parts[-1]] = value

        if persist:
            self.save()

    def save(self):
        """Save config to disk"""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, 'w') as f:
                yaml.dump(self._config, f, default_flow_style=False, sort_keys=False)
            logger.info(f"Saved config to {self.config_file}")
        except Exception as e:
            logger.error(f"Failed to save config: {e}")

    def start_watchdog(self, callback=None):
        """Start watching config directory for changes"""
        if self._observer:
            return

        self._reload_callback = callback or self.load
        self._observer = Observer()
        handler = ConfigChangeHandler(self._reload_callback)
        self._observer.schedule(handler, str(self.config_dir), recursive=False)
        self._observer.start()
        logger.info(f"Started config watchdog on {self.config_dir}")

    def stop_watchdog(self):
        """Stop the file watcher"""
        if self._observer:
            self._observer.stop()
            self._observer.join()
            self._observer = None
            logger.info("Stopped config watchdog")

    @property
    def raw_config(self) -> Dict[str, Any]:
        """Get raw config dict"""
        return self._config.copy()


# Global instance (lazy-initialized)
_config_engine: Optional[YAMLConfigEngine] = None


def get_config_engine(enable_watchdog: bool = False) -> YAMLConfigEngine:
    """Get or create global config engine"""
    global _config_engine
    if _config_engine is None:
        _config_engine = YAMLConfigEngine(enable_watchdog=enable_watchdog)
    return _config_engine
