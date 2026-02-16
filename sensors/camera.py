import time
import cv2
from picamera2 import Picamera2
import numpy as np
from pathlib import Path


def camera_process(input_queue, output_queue, duration=10):
    print("[Camera] Starting...")
    
    camera = _initialize_camera()
    tmp_dir = _setup_temp_directory()
    ref_gray = _capture_reference_background(camera)
    ignore_duration=2.0

    try:
        while True:
            data = input_queue.get()
            print(f"[Camera] Trigger #{data.get('trigger', '?')} - Streaming for {duration}s (ignoring first {ignore_duration}s)...")
            
            best_image, max_score = _capture_best_frame(
                camera, ref_gray, duration, ignore_duration
            )
            
            if best_image is not None:
                filename = _save_image(best_image, tmp_dir)
                data['image'] = filename
                data['sharpness'] = max_score
                output_queue.put(data)
                print(f"[Camera] Saved {filename} (Sharpness: {max_score:.1f})")
            else:
                print(f"[Camera] No object detected in {duration}s window")
                
    except KeyboardInterrupt:
        print("[Camera] Shutting down")
    finally:
        camera.stop()


def _initialize_camera():
    camera = Picamera2()
    config = camera.create_still_configuration(main={"size": (1920, 1080)})
    camera.configure(config)
    
    camera.set_controls({
        "ExposureTime": 1500,
        "AnalogueGain": 12.0,
        "AfMode": 0,
        "LensPosition": 5.0
    })
    
    camera.start()
    return camera


def _setup_temp_directory():
    script_dir = Path(__file__).parent
    tmp_dir = script_dir.parent / "data" / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"[Camera] Temp directory: {tmp_dir}")
    return tmp_dir


def _capture_reference_background(camera):
    print("[Camera] Calibrating background...")
    time.sleep(1)
    
    ref_request = camera.capture_request()
    ref_frame = np.ascontiguousarray(ref_request.make_array('main'))
    ref_request.release()
    
    ref_gray = cv2.cvtColor(ref_frame, cv2.COLOR_RGB2GRAY)
    return cv2.GaussianBlur(ref_gray, (21, 21), 0)


def _capture_best_frame(camera, ref_gray, duration, ignore_duration):
    best_image = None
    max_score = -1
    start_time = time.time()
    
    while (time.time() - start_time) < duration:
        bgr_frame = _capture_frame(camera)
        elapsed = time.time() - start_time
        
        # Skip frames during ignore period
        if elapsed < ignore_duration:
            continue
        
        # Check if object is present and evaluate sharpness
        if _object_detected(bgr_frame, ref_gray):
            score = _get_sharpness_score(bgr_frame)
            if score > max_score:
                max_score = score
                best_image = bgr_frame.copy()
    
    return best_image, max_score


def _capture_frame(camera):
    request = camera.capture_request()
    array_data = request.make_array('main')
    request.release()
    
    return cv2.cvtColor(np.ascontiguousarray(array_data), cv2.COLOR_RGB2BGR)


def _object_detected(bgr_frame, ref_gray, threshold=500):
    gray_frame = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2GRAY)
    gray_frame = cv2.GaussianBlur(gray_frame, (21, 21), 0)
    
    frame_delta = cv2.absdiff(ref_gray, gray_frame)
    thresh = cv2.threshold(frame_delta, 25, 255, cv2.THRESH_BINARY)[1]
    change_amount = np.sum(thresh) / 255
    
    return change_amount > threshold


def _get_sharpness_score(bgr_image):
    gray = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2GRAY)
    return cv2.Laplacian(gray, cv2.CV_64F).var()


def _save_image(image, tmp_dir):
    img_id = _get_next_image_number(tmp_dir)
    filename = tmp_dir / f"image_{img_id}.jpg"
    cv2.imwrite(str(filename), image)
    return str(filename)


def _get_next_image_number(tmp_dir):
    if not tmp_dir.exists():
        return 1
    
    files = [f for f in tmp_dir.iterdir() 
             if f.name.startswith("image_") and f.name.endswith(".jpg")]
    
    if not files:
        return 1
    
    nums = []
    for f in files:
        num_str = f.stem.replace("image_", "")
        if num_str.isdigit():
            nums.append(int(num_str))
    
    return max(nums) + 1 if nums else 1