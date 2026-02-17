import requests
import os
from datetime import datetime, timezone

class ClientSender:
    def __init__(self, frontend_api_url: str, photo_lambda_url: str = None, sensor_lambda_url: str = None, bin_id: str = None):
        self.frontend_api_url = frontend_api_url
        self.photo_lambda_url = photo_lambda_url
        self.sensor_lambda_url = sensor_lambda_url
        self.bin_id = bin_id
    
    def send(self, fullness: float, weight: float, image_path: str) -> dict:
        
        # Send to Front-End API (WasteRec)
        try:
            data = {'weight': weight, 'fullness': fullness}
            files = { 'image': ('image.jpg', open(image_path, 'rb'), 'image/jpeg')}
            
            response = requests.post(
                f"{self.frontend_api_url}/record",
                data=data,
                files=files,
                timeout=30
            )
            
            files['image'][1].close()  
            
            if response.status_code == 200 or response.status_code == 201:
                result = response.json()
                print(f"[API] Sent to Front-End API successfully")
                if result.get('inference_triggered'):
                    print(f"  Inference triggered: {result.get('inference_count')} total")
            else:
                print(f"[API] Front-End API returned status {response.status_code}")
                
        except requests.exceptions.ConnectionError as e:
            print(f"[API] Connection error: Cannot reach {self.frontend_api_url}")
        except Exception as e:
            print(f"[API] Send error to Front-End API: {e}")
        
        try:
            os.remove(image_path)
        except Exception as e:
            print(f"[DATA] Failed to remove image file {image_path}: {e}")
        
        return {
            'success': True,
            'response': None
        }

