from pathlib import Path

CONFIG = {
    # Pin Configurations (subject to change)
    "ir_gpio_pin": 5,  # IR sensor pin
    "ultrasonic_trig_pin": 23,  # Ultrasonic Trigger Pin
    "ultrasonic_echo_pin": 24,  # Ultrasonic Echo Pin
    "weight_dout_pin": 5,  # Weight Data Out Pin
    "weight_sck_pin": 6,  # Serial Clock Input Pin
    "camera_light_pin": 17,  # Camera light, on only while the camera is watching (None = no light)

    # Sensors to use. A disabled sensor is skipped and its reading is recorded as null.
    # Without IR, the camera's motion detection starts each cycle; without either, a timer does.
    "enable_ir": True,
    "enable_camera": True,
    "enable_ultrasonic": True,
    "enable_weight": False,  # No HX711 connected yet
    "no_trigger_interval": 30.0,  # Seconds between cycles when IR and camera are both disabled

    "ir_trigger_on": "clear",  # Trigger when the beam goes "clear" (lid opens) or "broken"
    "debounce_time": 3.0,  # Seconds to ignore after IR trigger
    "max_trigger_age": 2.0,  # Skip triggers that waited longer than this while the pipeline was busy
    "camera_duration": 10.0,  # Max seconds the camera watches for an object per trigger
    "image_size": (1920, 1080),  # Saved image resolution
    "detect_size": (320, 180),  # Low-res stream used for motion detection
    "camera_exposure_us": 2000,  # 1/500 s: less motion blur on thrown items; raise if dark items stop being detected
    "camera_gain": 16.0,  # Sensor maximum on the imx519 / imx219
    "camera_fps": 60,  # More frames = more chances to catch the object mid-air (lower if a Pi 3 can't keep up)
    "motion_min_area": 15,  # Min changed area (in detect_size pixels) that counts as an object
    "motion_ignore_bottom": 1 / 3,  # Fraction of the view (from the bottom) ignored for motion, where the lid swings
    "jpeg_quality": 90,
    "ultrasonic_samples": 5,  # Number of Samples from Ultrasonic
    "ultrasonic_settle_time": 3.0,  # Seconds after the object leaves the frame before measuring fullness
    "bin_empty_distance_cm": 66.7,  # Ultrasonic reading with the bin empty (measured) = 0% full
    "bin_full_distance_cm": 10.0,  # Reading at which the bin counts as 100% full
    "weight_samples": 10,  # Total Weight Samples
    "weight_settle_time": 3.0,  # Seconds after the object passes before weighing

    # On-device classifier (wasterec): which bin the captured item belongs in. Needs onnxruntime.
    "enable_classifier": True,
    "classifier_model": Path(__file__).parent / "models" / "wasterec_int8.onnx",
    "classifier_threshold": 0.6,  # Below this bin probability the fallback bin is used
    "classifier_fallback": "trash",  # "When in doubt, throw it out"
    "classifier_threads": 4,
    "classifier_crop_padding": 0.3,  # Margin around the detected item, as a fraction of its size

    "api_url": "",  # Front-End API base URL; records are spooled until this is set and reachable
    "spool_dir": Path(__file__).parent / "data" / "spool",
    "max_records": 1000,  # Oldest spooled records are deleted beyond this
    "upload_retry_interval": 10.0,
    "history_dir": Path(__file__).parent / "data" / "history",  # Uploaded records are kept here for the dashboard
    "max_history": 1000,  # Oldest history records are deleted beyond this

    # Local API the dashboard reads from (python -m data.local_api)
    "local_api_host": "127.0.0.1",  # Only the dashboard on this Pi talks to it
    "local_api_port": 8000,
}
