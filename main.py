#!/usr/bin/env python3
import logging
import multiprocessing as mp
import queue
import signal
import time

import cv2

from client.client import Uploader
from config import CONFIG
from data.spool import Spool
from sensors.camera import Camera
from sensors.ir_sensor import ir_sensor_process
from sensors.ultrasonic import Ultrasonic
from sensors.weight import Weight

log = logging.getLogger("Main")


def run_pipeline(cfg, triggers, stop, ir_process, camera, ultrasonic, weight, spool, uploader):
    while not stop.is_set():
        try:
            trigger = triggers.get(timeout=0.5)
        except queue.Empty:
            if not ir_process.is_alive():
                raise RuntimeError("IR sensor process died")
            continue

        age = time.monotonic() - trigger["ts"]
        if age > cfg["max_trigger_age"]:
            log.info("Skipping trigger #%d, it waited %.1fs", trigger["trigger"], age)
            continue

        log.info("-------- Cycle #%d --------", trigger["trigger"])
        result = camera.capture_pass(cfg["camera_duration"], stop_event=stop)
        camera.refresh_reference()
        if result is None:
            log.info("No object detected in %.0fs window", cfg["camera_duration"])
            continue
        frame, enter_time, exit_time = result

        # Do the ultrasonic reading and JPEG encoding while the load cell settles.
        distance = ultrasonic.measure(cfg["ultrasonic_samples"]) if ultrasonic else None
        ok, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, cfg["jpeg_quality"]])
        del frame
        if not ok:
            log.error("JPEG encoding failed")
            continue

        remaining = exit_time + cfg["weight_settle_time"] - time.monotonic()
        if remaining > 0:
            stop.wait(remaining)
        grams = weight.read_grams() if weight else None

        record_id = spool.add(jpeg.tobytes(), {
            "fullness": distance,
            "weight": grams,
            "transit_duration": round(exit_time - enter_time, 3),
        })
        uploader.wake()
        log.info("Stored %s: distance=%s cm, weight=%s g", record_id, _fmt(distance), _fmt(grams))


def _fmt(value):
    return "n/a" if value is None else f"{value:.2f}"


def _try_init(name, factory):
    """Optional sensors: log and carry on without them if they fail to start."""
    try:
        return factory()
    except Exception as e:
        log.error("%s unavailable: %s", name, e)
        return None


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    cfg = CONFIG
    stop = mp.Event()
    triggers = mp.Queue(maxsize=5)

    # Start the IR watcher before the camera and background threads exist, so the forked child starts clean.
    ir_process = mp.Process(
        target=ir_sensor_process,
        args=(triggers, stop, cfg["ir_gpio_pin"], cfg["debounce_time"]),
        name="ir_sensor",
        daemon=True,
    )
    ir_process.start()

    def request_stop(signum, frame):
        log.info("Shutting down...")
        stop.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    spool = Spool(cfg["spool_dir"], cfg["max_records"])
    uploader = Uploader(spool, cfg["api_url"], stop, cfg["upload_retry_interval"])
    uploader.start()

    camera = ultrasonic = weight = None
    try:
        camera = Camera(cfg["image_size"], cfg["detect_size"], cfg["motion_min_area"])
        ultrasonic = _try_init("Ultrasonic", lambda: Ultrasonic(
            cfg["ultrasonic_trig_pin"], cfg["ultrasonic_echo_pin"]))
        weight = _try_init("Weight", lambda: Weight(
            cfg["weight_dout_pin"], cfg["weight_sck_pin"], cfg["weight_samples"]))

        log.info("-------------------- Ready --------------------")
        run_pipeline(cfg, triggers, stop, ir_process, camera, ultrasonic, weight, spool, uploader)
    finally:
        stop.set()
        uploader.wake()
        for device in (camera, ultrasonic, weight):
            if device is not None:
                device.close()
        ir_process.join(timeout=2)
        if ir_process.is_alive():
            ir_process.terminate()
        uploader.join(timeout=5)


if __name__ == "__main__":
    main()
