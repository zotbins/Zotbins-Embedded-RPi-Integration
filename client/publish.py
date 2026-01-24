"""
publish.py - Publish to AWS server both sensor data and captured photo.
"""

import requests
import json
import base64

# Endpoint Info (protect/hide these later)
SENSOR_DATA_ENDPOINT = "https://your-api-url.amazonaws.com/upload-sensor-data"
PHOTO_ENDPOINT = "https://your-api-url.amazonaws.com/upload-photo"
BIN_ID = "1" 
MCU_TYPE = "raspberry_pi"

# Bin physical parameters (currently dummy values)
BIN_HEIGHT_CM = 50.0 
OVERFLOW_THRESHOLD_CM = 5.0  


def publish_sensor_data(bin_id, fullness, overflow, weight):
    """
    Send sensor data to AWS endpoint
    """
    payload = {
        "bin_id": str(bin_id),
        "mcu_type": MCU_TYPE,
        "fullness": float(fullness),
        "usage": 0, 
        "overflow": 1 if overflow else 0,
        "weight": float(weight)
    }
    
    try:
        print(f"[Publish] Sending sensor data to AWS...")
        
        response = requests.put(
            SENSOR_DATA_ENDPOINT,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        
        if response.status_code == 200:
            print(f"[Publish Success] Sensor data uploaded (Status: {response.status_code})")
            return True
        else:
            print(f"[Publish Failure] Sensor data failed (Status: {response.status_code})")
            print(f"[Publish Failure] Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"[Publish Failure] Sensor data error: {e}")
        return False
    

def publish_photo(bin_id, image_path):
    """
    Send photo to AWS endpoint as base64
    """
    
    try:
        # Read image and convert to base64
        with open(image_path, 'rb') as image_file:
            image_bytes = image_file.read()
            image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        
        payload = {
            "bin_id": str(bin_id),
            "mcu_type": MCU_TYPE,
            "photo": image_base64  # base64-encoded image as string
        }
        
        print(f"[Publish] Sending photo to AWS ({len(image_base64)} chars base64)...")
        
        response = requests.put(
            PHOTO_ENDPOINT,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30  
        )
        
        if response.status_code == 200:
            print(f"[Publish Complete] Photo uploaded (Status: {response.status_code})")
            return True
        else:
            print(f"[Publish Failure] Photo failed (Status: {response.status_code})")
            print(f"[Publish Failure] Response: {response.text}")
            return False
            
    except FileNotFoundError:
        print(f"[Publish Failure] File not found: {image_path}")
        return False
    except Exception as e:
        print(f"[Publish Failure] Photo error: {e}")
        return False


def publish(bin_id, result):
    """
    Publish both sensor data and photo from final result (produced from main.py)
    """
    
    # Calculate fullness from distance
    distance = result['distance']
    fullness = max(0.0, min(1.0, 1.0 - (distance / BIN_HEIGHT_CM)))
    
    # Check if overflowing
    overflow = distance < OVERFLOW_THRESHOLD_CM
    
    # Get weight and image
    weight = result['weight']
    image_path = result['image']
    
    # Publish sensor data
    sensor_success = publish_sensor_data(bin_id, fullness, overflow, weight)
    
    # Publish photo
    photo_success = publish_photo(bin_id, image_path)
    
    if sensor_success and photo_success:
        print(f"[Publish Complete] All data uploaded to AWS successfully")

    return {
        'sensor_data': sensor_success,
        'photo': photo_success,
        'all_success': sensor_success and photo_success
    }