"""Raspberry Pi camera wrapper (picamera2). Kept open so repeated captures are fast."""
import time


class PiCamera:
    def __init__(self, size=(1280, 960), warmup=1.0):
        from picamera2 import Picamera2  # only available on the Pi (sudo apt install python3-picamera2)

        self.cam = Picamera2()
        self.cam.configure(self.cam.create_still_configuration(main={"size": size, "format": "RGB888"}))
        self.cam.start()
        time.sleep(warmup)  # let auto-exposure settle in low light

    def capture(self):
        return self.cam.capture_array()  # RGB888 is BGR byte order, as OpenCV expects

    def close(self):
        self.cam.stop()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
