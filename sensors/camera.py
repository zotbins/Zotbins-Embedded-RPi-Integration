import logging
import time

import cv2
import RPi.GPIO as GPIO
from picamera2 import Picamera2

log = logging.getLogger("Camera")

LIGHT_SETTLE_S = 0.2  # Frames already queued were taken before the light came on; discard this long


class Camera:
    """Detects motion on a small low-res stream and keeps a few full-res frames of the object passing.

    The ISP produces the low-res stream alongside the main one at no extra CPU cost,
    so motion detection works on ~57k pixels per frame instead of millions.
    """

    def __init__(self, image_size=(1920, 1080), detect_size=(320, 180),
                 min_contour_area=15, max_kept_frames=8, light_pin=None):
        self.detect_w, self.detect_h = detect_size
        self.min_contour_area = min_contour_area
        self.max_kept_frames = max_kept_frames
        self.light_pin = light_pin

        if light_pin is not None:
            GPIO.setwarnings(False)
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(light_pin, GPIO.OUT, initial=GPIO.LOW)

        self.picam = Picamera2()
        # "RGB888" is stored as B,G,R in memory, which is what OpenCV expects, so no conversion is needed.
        # On Pi 3/4 the lores stream must be YUV420; its first plane is the grayscale image.
        config = self.picam.create_video_configuration(
            main={"size": image_size, "format": "RGB888"},
            lores={"size": detect_size, "format": "YUV420"},
            buffer_count=4,
        )
        self.picam.configure(config)
        controls = {
            "ExposureTime": 1500,
            "AnalogueGain": 18.0,
        }
        # Manual focus only exists on autofocus modules (Camera Module 3); v2 / imx219 is fixed-focus.
        if "AfMode" in self.picam.camera_controls:
            controls.update({"AfMode": 0, "LensPosition": 5.0})
        self.picam.set_controls(controls)
        self.picam.start()

        log.info("Calibrating background...")
        time.sleep(1)
        # The reference is taken with the light on, since that's how every pass is watched.
        self._light_on()
        try:
            self.refresh_reference()
        finally:
            self._light_off()

    def close(self):
        self.picam.stop()
        self.picam.close()
        if self.light_pin is not None:
            self._light_off()
            # Only release our own pin; GPIO.cleanup() with no args would reset every pin.
            GPIO.cleanup(self.light_pin)

    def _light_on(self):
        if self.light_pin is None:
            return
        GPIO.output(self.light_pin, GPIO.HIGH)
        end = time.monotonic() + LIGHT_SETTLE_S
        while time.monotonic() < end:
            self.picam.capture_request().release()

    def _light_off(self):
        if self.light_pin is not None:
            GPIO.output(self.light_pin, GPIO.LOW)

    def refresh_reference(self):
        """Re-capture the empty background. Call with the light on."""
        request = self.picam.capture_request()
        try:
            self.reference = self._detect_gray(request)
        finally:
            request.release()

    def snapshot(self):
        """Grab the current full-res frame (BGR), with the light on."""
        self._light_on()
        try:
            request = self.picam.capture_request()
            try:
                return request.make_array("main")
            finally:
                request.release()
        finally:
            self._light_off()

    def capture_pass(self, duration, ignore_duration=0.1, exit_grace=0.3, stop_event=None):
        """Watch for an object passing through view, with the light on.

        Afterwards the empty background is re-captured while the light is still on, so
        lighting changes over the day don't cause false detections on the next pass.

        Returns (frame, enter_time, exit_time) with times from time.monotonic(), or None if nothing was seen.
        """
        self._light_on()
        try:
            result = self._watch(duration, ignore_duration, exit_grace, stop_event)
            self.refresh_reference()
            return result
        finally:
            self._light_off()

    def _watch(self, duration, ignore_duration, exit_grace, stop_event):
        kept = []  # (timestamp, full-res frame), spread evenly over the pass
        stride = 1
        detections = 0
        enter_time = last_seen = None
        start = time.monotonic()

        while time.monotonic() - start < duration:
            if stop_event is not None and stop_event.is_set():
                break

            request = self.picam.capture_request()
            try:
                now = time.monotonic()
                if now - start < ignore_duration:
                    continue

                if self._motion_detected(self._detect_gray(request)):
                    if enter_time is None:
                        enter_time = now
                        log.info("Object entered at +%.3fs", now - start)
                    last_seen = now

                    # Only copy the full-res frame when we're keeping it. When the buffer fills,
                    # drop every other frame so memory stays bounded however long the pass lasts.
                    if detections % stride == 0:
                        kept.append((now, request.make_array("main")))
                        if len(kept) > self.max_kept_frames:
                            kept = kept[::2]
                            stride *= 2
                    detections += 1

                elif enter_time is not None and now - last_seen >= exit_grace:
                    log.info("Object exited at +%.3fs", last_seen - start)
                    break
            finally:
                request.release()

        if enter_time is None:
            return None

        mid_time = (enter_time + last_seen) / 2
        _, frame = min(kept, key=lambda item: abs(item[0] - mid_time))
        return frame, enter_time, last_seen

    def _detect_gray(self, request):
        yuv = request.make_array("lores")
        gray = yuv[:self.detect_h, :self.detect_w]
        return cv2.GaussianBlur(gray, (5, 5), 0)

    def _motion_detected(self, gray):
        frame_delta = cv2.absdiff(self.reference, gray)
        thresh = cv2.threshold(frame_delta, 25, 255, cv2.THRESH_BINARY)[1]

        # Dilate to close small gaps in contiguous regions
        thresh = cv2.dilate(thresh, None, iterations=2)

        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        return any(cv2.contourArea(c) >= self.min_contour_area for c in contours)


if __name__ == "__main__":
    # Standalone test: python -m sensors.camera [--duration S] [--out DIR]
    # Each time you press Enter it watches for an object and saves the frame it would have picked.
    # With --delay S it instead takes a picture after S seconds (--count N pictures, 0 = until Ctrl+C).
    import argparse
    from pathlib import Path

    from config import CONFIG

    parser = argparse.ArgumentParser(description="Capture object passes and save the selected frame.")
    parser.add_argument("--duration", type=float, default=CONFIG["camera_duration"])
    parser.add_argument("--min-area", type=int, default=CONFIG["motion_min_area"])
    parser.add_argument("--out", type=Path, default=Path(__file__).parent.parent / "data" / "camera_test")
    parser.add_argument("--delay", type=float, default=None,
                        help="take a picture after this many seconds instead of detecting motion")
    parser.add_argument("--count", type=int, default=1, help="pictures to take with --delay (0 = until Ctrl+C)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s", datefmt="%H:%M:%S")

    args.out.mkdir(parents=True, exist_ok=True)
    camera = Camera(CONFIG["image_size"], CONFIG["detect_size"], args.min_area,
                    light_pin=CONFIG["camera_light_pin"])
    try:
        if args.delay is not None:
            n = 0
            while args.count == 0 or n < args.count:
                n += 1
                print(f"Picture {n} in {args.delay:g}s...", flush=True)
                time.sleep(args.delay)
                path = args.out / f"snapshot_{time.strftime('%Y%m%d_%H%M%S')}_{n}.jpg"
                cv2.imwrite(str(path), camera.snapshot())
                print(f"Saved {path}")
            raise SystemExit

        for n in range(1, 1_000_000):
            input(f"\nPress Enter, then pass an object in front of the camera ({args.duration:.0f}s window). Ctrl+C to quit.")
            result = camera.capture_pass(args.duration)
            if result is None:
                print("No object detected")
                continue
            frame, enter_time, exit_time = result
            path = args.out / f"capture_{n}.jpg"
            cv2.imwrite(str(path), frame)
            print(f"Saved {path} (in view {exit_time - enter_time:.2f}s)")
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        camera.close()
