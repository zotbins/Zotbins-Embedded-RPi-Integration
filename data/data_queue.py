import sqlite3
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional


class DataQueue:
    def __init__(self, db_path: str = "data.db", 
                 image_dir: str = "images",
                 max_records: int = 1000):
        script_dir = Path(__file__).parent
        self.db_path = str(script_dir / db_path)
        self.image_dir = script_dir / Path(image_dir)
        self.max_records = max_records
        
        self._setup_storage()
        self._init_database()
    
    def _setup_storage(self):
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.image_dir.mkdir(parents=True, exist_ok=True)
    
    def _init_database(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sensor_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    fullness REAL NOT NULL,
                    weight REAL NOT NULL,
                    image_path TEXT NOT NULL,
                    uploaded INTEGER DEFAULT 0,
                    upload_attempts INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp 
                ON sensor_data(timestamp DESC)
            """)
            
            conn.commit()
    
    def add_record(self, fullness: float, weight: float, 
                   image_path: str, timestamp: Optional[str] = None) -> int:
        if timestamp is None:
            timestamp = datetime.now().isoformat()
        
        dest_image_path = self._save_image(image_path, timestamp)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO sensor_data (timestamp, fullness, weight, image_path)
                VALUES (?, ?, ?, ?)
            """, (timestamp, fullness, weight, str(dest_image_path)))
            
            record_id = cursor.lastrowid
            
            self._cleanup_old_records(cursor)
            conn.commit()
        
        return record_id
    
    def _save_image(self, source_path: str, timestamp: str) -> Path:
        safe_timestamp = timestamp.replace(':', '-').replace('.', '_')
        image_filename = f"img_{safe_timestamp}.jpg"
        dest_path = self.image_dir / image_filename
        
        shutil.copy2(source_path, dest_path)
        
        return dest_path
    
    def _cleanup_old_records(self, cursor):
        cursor.execute("SELECT COUNT(*) FROM sensor_data")
        count = cursor.fetchone()[0]
        
        if count <= self.max_records:
            return
        
        num_to_delete = count - self.max_records
        records_to_delete = self._get_oldest_records(cursor, num_to_delete)
        
        self._delete_image_files(records_to_delete)
        self._delete_database_records(cursor, records_to_delete)
        
        print(f"[DataQueue] Cleaned up {num_to_delete} old records")
    
    def _get_oldest_records(self, cursor, num_to_delete: int) -> list:
        cursor.execute("""
            SELECT id, image_path FROM sensor_data 
            ORDER BY timestamp ASC 
            LIMIT ?
        """, (num_to_delete,))
        
        return cursor.fetchall()
    
    def _delete_image_files(self, records: list):
        for record_id, image_path in records:
            try:
                if os.path.exists(image_path):
                    os.remove(image_path)
            except Exception as e:
                print(f"[DataQueue] Warning: Could not delete image {image_path}: {e}")
    
    def _delete_database_records(self, cursor, records: list):
        ids_to_delete = [record[0] for record in records]
        placeholders = ','.join('?' * len(ids_to_delete))
        cursor.execute(
            f"DELETE FROM sensor_data WHERE id IN ({placeholders})", 
            ids_to_delete
        )