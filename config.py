from pathlib import Path

CONFIG = {
    # Pin Configurations (subject to change)
    "ir_gpio_pin": 5,  # IR sensor pin
    "ultrasonic_trig_pin": 23,  # Ultrasonic Trigger Pin
    "ultrasonic_echo_pin": 24,  # Ultrasonic Echo Pin
    "weight_dout_pin": 5,  # Weight Data Out Pin
    "weight_sck_pin": 6,  # Serial Clock Input Pin

    "debounce_time": 3.0,  # Seconds to ignore after IR trigger
    "max_trigger_age": 2.0,  # Skip triggers that waited longer than this while the pipeline was busy
    "camera_duration": 10.0,  # Max seconds the camera watches for an object per trigger
    "image_size": (1920, 1080),  # Saved image resolution
    "detect_size": (320, 180),  # Low-res stream used for motion detection
    "motion_min_area": 15,  # Min changed area (in detect_size pixels) that counts as an object
    "jpeg_quality": 90,
    "ultrasonic_samples": 5,  # Number of Samples from Ultrasonic
    "weight_samples": 10,  # Total Weight Samples
    "weight_settle_time": 3.0,  # Seconds after the object passes before weighing

    "api_url": "",  # Front-End API base URL; records are spooled until this is set and reachable
    "spool_dir": Path(__file__).parent / "data" / "spool",
    "max_records": 1000,  # Oldest spooled records are deleted beyond this
    "upload_retry_interval": 10.0,
}
