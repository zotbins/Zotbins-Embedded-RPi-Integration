from data.data_queue import DataQueue
from datetime import datetime
import json


class DataStore:
    def __init__(self, max_records: int = 1000):
        self.queue = DataQueue(
            db_path="data.db",
            image_dir="images",
            max_records=max_records
        )
    
    def store(self, fullness: float, weight: float, image_path: str) -> int:
        record_id = self.queue.add_record(
            fullness=fullness,
            weight=weight,
            image_path=image_path
        )
        
        print(f"[DATA] Stored record {record_id} locally")
        return record_id
    
    
