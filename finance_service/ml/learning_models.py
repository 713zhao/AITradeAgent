

# Migration Helper Functions
# ===========================

def migrate_learning_layer1(db) -> bool:
    """
    Initialize Layer 1 trade_analysis table if it doesn't exist.
    
    Args:
        db: Database connection object
    
    Returns:
        True if migration succeeded or table already exists
    """
    try:
        cursor = db.connection.cursor()
        
        # Check if table already exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='trade_analysis'"
        )
        if cursor.fetchone() is not None:
            return True  # Already exists
        
        # Create table
        cursor.execute('''
            CREATE TABLE trade_analysis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id TEXT NOT NULL UNIQUE,
                symbol TEXT NOT NULL,
                entry_score REAL NOT NULL CHECK (entry_score >= 0 AND entry_score <= 10),
                skill_vs_luck_ratio REAL NOT NULL CHECK (skill_vs_luck_ratio >= 0 AND skill_vs_luck_ratio <= 1),
                pattern_type TEXT NOT NULL,
                mistakes TEXT NOT NULL DEFAULT '[]',
                psychological_notes TEXT NOT NULL DEFAULT '[]',
                recommendations TEXT NOT NULL DEFAULT '[]',
                tags TEXT NOT NULL DEFAULT '[]',
                llm_response TEXT NOT NULL DEFAULT '{}',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create indices
        cursor.execute('CREATE INDEX idx_trade_analysis_trade_id ON trade_analysis(trade_id)')
        cursor.execute('CREATE INDEX idx_trade_analysis_symbol ON trade_analysis(symbol)')
        cursor.execute('CREATE INDEX idx_trade_analysis_pattern ON trade_analysis(pattern_type)')
        cursor.execute('CREATE INDEX idx_trade_analysis_created ON trade_analysis(created_at)')
        
        db.connection.commit()
        return True
    except Exception as e:
        print(f"Layer 1 migration failed: {e}")
        return False


def insert_trade_analysis_layer1(db, analysis: TradeAnalysisLayer1) -> bool:
    """
    Insert a Layer 1 trade analysis result into the database.
    
    Args:
        db: Database connection
        analysis: TradeAnalysisLayer1 dataclass instance
    
    Returns:
        True if insert succeeded
    """
    try:
        cursor = db.connection.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO trade_analysis (
                trade_id, symbol, entry_score, skill_vs_luck_ratio, pattern_type,
                mistakes, psychological_notes, recommendations, tags, llm_response, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', analysis.to_db_tuple())
        db.connection.commit()
        return True
    except Exception as e:
        print(f"Failed to insert trade analysis: {e}")
        return False


def get_trade_analysis_layer1(db, trade_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a Layer 1 trade analysis by trade_id.
    
    Args:
        db: Database connection
        trade_id: Trade ID to look up
    
    Returns:
        Dictionary with analysis data or None if not found
    """
    try:
        cursor = db.connection.cursor()
        cursor.execute(
            '''SELECT * FROM trade_analysis WHERE trade_id = ?''',
            (trade_id,)
        )
        row = cursor.fetchone()
        if row is None:
            return None
        
        # Convert row to dict
        return {
            'id': row[0],
            'trade_id': row[1],
            'symbol': row[2],
            'entry_score': row[3],
            'skill_vs_luck_ratio': row[4],
            'pattern_type': row[5],
            'mistakes': json.loads(row[6]),
            'psychological_notes': json.loads(row[7]),
            'recommendations': json.loads(row[8]),
            'tags': json.loads(row[9]),
            'llm_response': json.loads(row[10]),
            'created_at': row[11]
        }
    except Exception as e:
        print(f"Failed to retrieve trade analysis: {e}")
        return None


def query_trade_analysis_by_symbol(db, symbol: str, limit: int = 100) -> List[Dict[str, Any]]:
    """
    Query all trade analyses for a given symbol.
    
    Args:
        db: Database connection
        symbol: Trading symbol
        limit: Max results to return
    
    Returns:
        List of analysis dictionaries
    """
    try:
        cursor = db.connection.cursor()
        cursor.execute(
            '''SELECT * FROM trade_analysis WHERE symbol = ? ORDER BY created_at DESC LIMIT ?''',
            (symbol, limit)
        )
        rows = cursor.fetchall()
        
        results = []
        for row in rows:
            results.append({
                'id': row[0],
                'trade_id': row[1],
                'symbol': row[2],
                'entry_score': row[3],
                'skill_vs_luck_ratio': row[4],
                'pattern_type': row[5],
                'mistakes': json.loads(row[6]),
                'psychological_notes': json.loads(row[7]),
                'recommendations': json.loads(row[8]),
                'tags': json.loads(row[9]),
                'llm_response': json.loads(row[10]),
                'created_at': row[11]
            })
        
        return results
    except Exception as e:
        print(f"Failed to query trade analyses: {e}")
        return []
