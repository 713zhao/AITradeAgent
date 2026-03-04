"""Caching layer for market data"""
import sqlite3
import json
import time
from pathlib import Path
from typing import Any, Optional, Dict
from .config import Config

class Cache:
    """SQLite-backed cache for market data and indicators"""
    
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or Config.CACHE_FILE
        self._init_db()
    
    def _init_db(self):
        """Initialize cache database schema"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    ttl_seconds INTEGER DEFAULT 3600
                )
            """)
            conn.commit()
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT value, timestamp, ttl_seconds FROM cache WHERE key = ?",
                (key,)
            )
            row = cursor.fetchone()
        
        if not row:
            return None
        
        value, timestamp, ttl = row
        if time.time() - timestamp > ttl:
            self.delete(key)
            return None
        
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    
    def set(self, key: str, value: Any, ttl_seconds: int = 3600):
        """Store value in cache with TTL"""
        json_value = json.dumps(value) if not isinstance(value, str) else value
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO cache (key, value, timestamp, ttl_seconds)
                VALUES (?, ?, ?, ?)
                """,
                (key, json_value, time.time(), ttl_seconds)
            )
            conn.commit()
    
    def delete(self, key: str):
        """Delete value from cache"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM cache WHERE key = ?", (key,))
            conn.commit()
    
    def clear(self):
        """Clear entire cache"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM cache")
            conn.commit()
    
    def cleanup_expired(self):
        """Remove expired entries"""
        current_time = time.time()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                DELETE FROM cache 
                WHERE timestamp + ttl_seconds < ?
                """,
                (current_time,)
            )
            conn.commit()
