"""Feature Store - Central repository for trading features and labels.

Stores features (technical, fundamental, news, options, regime) symbol-date pairs.
Used for training ML models and online inference.
"""
import logging
import os
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, date
from dataclasses import dataclass, asdict
import pandas as pd
import numpy as np
from pathlib import Path
import sqlite3
import json

logger = logging.getLogger(__name__)


@dataclass
class FeatureRecord:
    """Single feature record for a symbol/date"""
    symbol: str
    date: date
    features: Dict[str, float]  # feature_name -> value
    label: Optional[float] = None  # e.g., forward return, trade outcome
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class FeatureStore:
    """SQLite-backed feature store with versioning.

    Schema:
        features (symbol, date, feature_name, feature_value, version)
        labels (symbol, date, label_type, label_value)
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.path.join(os.getenv("STORAGE_DIR", "storage"), "feature_store.db")
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Create tables if needed"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS features (
                    symbol TEXT,
                    date DATE,
                    feature_name TEXT,
                    feature_value REAL,
                    version INTEGER DEFAULT 1,
                    PRIMARY KEY (symbol, date, feature_name)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS labels (
                    symbol TEXT,
                    date DATE,
                    label_type TEXT,
                    label_value REAL,
                    PRIMARY KEY (symbol, date, label_type)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_features_symbol_date ON features(symbol, date)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_labels_symbol_date ON labels(symbol, date)")
            conn.commit()

    def save_features(self, record: FeatureRecord, overwrite: bool = True):
        """Save a feature record (multiple features in one transaction)"""
        if not record.features:
            return
        with sqlite3.connect(self.db_path) as conn:
            for name, value in record.features.items():
                if overwrite:
                    conn.execute("""
                        INSERT OR REPLACE INTO features (symbol, date, feature_name, feature_value, version)
                        VALUES (?, ?, ?, ?, COALESCE(
                            (SELECT version FROM features WHERE symbol=? AND date=? AND feature_name=?), 1) + 1)
                    """, (record.symbol, record.date.isoformat(), name, value, record.symbol, record.date.isoformat(), name))
                else:
                    conn.execute("""
                        INSERT INTO features (symbol, date, feature_name, feature_value)
                        VALUES (?, ?, ?, ?)
                    """, (record.symbol, record.date.isoformat(), name, value))
            conn.commit()

    def load_features(
        self,
        symbols: List[str],
        start_date: date,
        end_date: date,
        feature_names: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """Load features into wide DataFrame (rows = symbol-date, cols = features)"""
        query = """
            SELECT symbol, date, feature_name, feature_value
            FROM features
            WHERE symbol IN ({}) AND date BETWEEN ? AND ?
        """.format(','.join('?' * len(symbols)))
        params = list(symbols) + [start_date.isoformat(), end_date.isoformat()]
        
        if feature_names:
            query += " AND feature_name IN ({})".format(','.join('?' * len(feature_names)))
            params.extend(feature_names)
        
        with sqlite3.connect(self.db_path) as conn:
            df = pd.read_sql_query(query, conn, params=params)
        
        if df.empty:
            return pd.DataFrame()
        
        # Pivot to wide format
        df_wide = df.pivot_table(index=['symbol', 'date'], columns='feature_name', values='feature_value', aggfunc='first')
        df_wide = df_wide.reset_index()
        return df_wide

    def save_label(self, symbol: str, date: date, label_type: str, value: float):
        """Save a label (outcome) for a symbol/date"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO labels (symbol, date, label_type, label_value)
                VALUES (?, ?, ?, ?)
            """, (symbol, date.isoformat(), label_type, value))
            conn.commit()

    def load_dataset(
        self,
        start_date: date,
        end_date: date,
        symbols: Optional[List[str]] = None,
        feature_names: Optional[List[str]] = None,
        label_type: str = "forward_return_5d"
    ) -> Tuple[pd.DataFrame, pd.Series]:
        """Load ML dataset: X (features) and y (label)"""
        # Determine symbols if not provided
        if symbols is None:
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.execute("SELECT DISTINCT symbol FROM features WHERE date BETWEEN ? AND ?", 
                                 (start_date.isoformat(), end_date.isoformat()))
                symbols = [row[0] for row in cur.fetchall()]
        
        # Load features
        X = self.load_features(symbols, start_date, end_date, feature_names)
        if X.empty:
            return pd.DataFrame(), pd.Series(dtype=float)
        
        # Load labels
        with sqlite3.connect(self.db_path) as conn:
            query = """
                SELECT symbol, date, label_value
                FROM labels
                WHERE label_type = ? AND symbol IN ({}) AND date BETWEEN ? AND ?
            """.format(','.join('?' * len(symbols)))
            params = [label_type] + symbols + [start_date.isoformat(), end_date.isoformat()]
            labels_df = pd.read_sql_query(query, conn, params=params)
        
        if labels_df.empty:
            logger.warning(f"No labels found for type={label_type}")
            return X, pd.Series()
        
        # Merge features with labels
        X['date'] = pd.to_datetime(X['date']).dt.date
        labels_df['date'] = pd.to_datetime(labels_df['date']).dt.date
        merged = X.merge(labels_df, on=['symbol', 'date'], how='inner')
        
        # Separate X and y
        feature_cols = [c for c in merged.columns if c not in ['symbol', 'date', 'label_value']]
        X_out = merged[['symbol', 'date'] + feature_cols]
        y_out = merged['label_value']
        
        return X_out, y_out
