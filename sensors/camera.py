import time
import cv2
from picamera2 import Picamera2
import numpy as np
from pathlib import Path
import libcamera


def camera_process(input_queue, output_queue, duration=10):
    print("[Camera] Starting...")
    
    camera = _initialize_camera()
    tmp_dir = _setup_temp_directory()
    ref_gray = _capture_reference_background(camera)
    ignore_duration = 0.1

    try:
        while True:
            data = input_queue.get()
            print(f"[Camera] Trigger #{data.get('trigger', '?')}")
            
            result = _capture_object_pass(
                camera, ref_gray, duration, ignore_duration
            )
            
            if result is not None:
                mid_frame, enter_time, exit_time = result
                filename = _save_image(mid_frame, tmp_dir)
                data['image'] = filename
                data['enter_time'] = enter_time
                data['exit_time'] = exit_time
                data['transit_duration'] = exit_time - enter_time
                output_queue.put(data)
                print(f"[Camera] Saved {filename} (transit: {exit_time - enter_time:.3f}s)")
            else:
                print(f"[Camera] No object detected in {duration}s window")
                
    except KeyboardInterrupt:
        print("[Camera] Shutting down")
    finally:
        camera.stop()


def _initialize_camera():
    camera = Picamera2()
    config = camera.create_still_configuration(main={"size": (3840, 2160)})
    camera.configure(config) 
    
    camera.set_controls({
        "ExposureTime": 1500,
        "AnalogueGain": 18.0,
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


def _capture_object_pass(camera, ref_gray, duration, ignore_duration,
                         min_contour_area=2000, exit_grace=0.3):
    frames = [] 
    enter_time = None
    last_detected_time = None
    start_time = time.time()
    
    while (time.time() - start_time) < duration:
        bgr_frame = _capture_frame(camera)
        now = time.time()
        elapsed = now - start_time
        
        if elapsed < ignore_duration:
            continue
        
        detected = _object_detected_contiguous(bgr_frame, ref_gray, min_contour_area)
        
        if detected:
            if enter_time is None:
                enter_time = now
                print(f"[Camera] Object entered at +{elapsed:.3f}s")
            
            last_detected_time = now
            frames.append((now, bgr_frame.copy()))
        
        else:
            if enter_time is not None:
                time_since_last = now - last_detected_time
                if time_since_last >= exit_grace:
                    exit_time = last_detected_time
                    print(f"[Camera] Object exited at +{exit_time - start_time:.3f}s")
                    
                    mid_frame = _select_middle_frame(frames, enter_time, exit_time)
                    return mid_frame, enter_time, exit_time
    
    # Duration expired — if we saw an object but it never "exited", use what we have
    if enter_time is not None and frames:
        exit_time = last_detected_time
        print(f"[Camera] Duration expired, using last detection as exit at +{exit_time - start_time:.3f}s")
        mid_frame = _select_middle_frame(frames, enter_time, exit_time)
        return mid_frame, enter_time, exit_time
    
    return None


def _capture_frame(camera):
    request = camera.capture_request()
    array_data = request.make_array('main')
    request.release()
    
    return cv2.cvtColor(np.ascontiguousarray(array_data), cv2.COLOR_RGB2BGR)


def _object_detected_contiguous(bgr_frame, ref_gray, min_contour_area=2000):
    
    gray_frame = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2GRAY)
    gray_frame = cv2.GaussianBlur(gray_frame, (21, 21), 0)
    
    frame_delta = cv2.absdiff(ref_gray, gray_frame)
    thresh = cv2.threshold(frame_delta, 25, 255, cv2.THRESH_BINARY)[1]
    
    # Dilate to close small gaps in contiguous regions
    thresh = cv2.dilate(thresh, None, iterations=2)
    
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    for contour in contours:
        if cv2.contourArea(contour) >= min_contour_area:
            return True
    
    return False


def _select_middle_frame(frames, enter_time, exit_time):
    mid_time = (enter_time + exit_time) / (2**0.5)
    
    best_frame = None
    best_diff = float('inf')
    
    for timestamp, frame in frames:
        diff = abs(timestamp - mid_time)
        if diff < best_diff:
            best_diff = diff
            best_frame = frame
    
    return best_frame


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