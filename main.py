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


def run_pipeline(cfg, stop, triggers, ir_process, camera, ultrasonic, weight, spool, uploader):
    while not stop.is_set():
        event = _next_event(cfg, stop, triggers, ir_process, camera)
        if event is None:
            continue
        frame, event_time, transit = event

        # Do the ultrasonic reading and JPEG encoding while the load cell settles.
        distance = ultrasonic.measure(cfg["ultrasonic_samples"]) if ultrasonic else None
        jpeg = None
        if frame is not None:
            ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, cfg["jpeg_quality"]])
            jpeg = encoded.tobytes() if ok else None
            if not ok:
                log.error("JPEG encoding failed; storing record without image")
        del frame

        grams = None
        if weight:
            remaining = event_time + cfg["weight_settle_time"] - time.monotonic()
            if remaining > 0:
                stop.wait(remaining)
            grams = weight.read_grams()

        record_id = spool.add(jpeg, {
            "fullness": distance,
            "weight": grams,
            "transit_duration": None if transit is None else round(transit, 3),
        })
        uploader.wake()
        log.info("Stored %s: image=%s, distance=%s cm, weight=%s g",
                 record_id, "yes" if jpeg else "no", _fmt(distance), _fmt(grams))


def _next_event(cfg, stop, triggers, ir_process, camera):
    """Wait for the next item to go in the bin.

    Returns (frame or None, monotonic time it passed, seconds in view or None), or None if nothing happened.
    """
    if ir_process is not None:
        trigger = _wait_for_trigger(cfg, stop, triggers, ir_process)
        if trigger is None:
            return None
        log.info("-------- Cycle #%d --------", trigger["trigger"])
        if camera is None:
            return None, trigger["ts"], None
        return _watch_camera(cfg, stop, camera, report_empty=True)

    if camera is not None:
        # No IR sensor: the camera's motion detection is the trigger.
        return _watch_camera(cfg, stop, camera, report_empty=False)

    # Neither IR nor camera: run on a timer.
    if stop.wait(cfg["no_trigger_interval"]):
        return None
    return None, time.monotonic(), None


def _wait_for_trigger(cfg, stop, triggers, ir_process):
    try:
        trigger = triggers.get(timeout=0.5)
    except queue.Empty:
        if not ir_process.is_alive():
            raise RuntimeError("IR sensor process died")
        return None

    age = time.monotonic() - trigger["ts"]
    if age > cfg["max_trigger_age"]:
        log.info("Skipping trigger #%d, it waited %.1fs", trigger["trigger"], age)
        return None
    return trigger


def _watch_camera(cfg, stop, camera, report_empty):
    result = camera.capture_pass(cfg["camera_duration"], stop_event=stop)
    camera.refresh_reference()
    if result is None:
        if report_empty:
            log.info("No object detected in %.0fs window", cfg["camera_duration"])
        return None
    frame, enter_time, exit_time = result
    return frame, exit_time, exit_time - enter_time


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
    log.info("Sensors: IR=%s camera=%s ultrasonic=%s weight=%s", *(
        "on" if cfg[key] else "off"
        for key in ("enable_ir", "enable_camera", "enable_ultrasonic", "enable_weight")))

    # Start the IR watcher before the camera and background threads exist, so the forked child starts clean.
    ir_process = None
    if cfg["enable_ir"]:
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
        if cfg["enable_camera"]:
            camera = Camera(cfg["image_size"], cfg["detect_size"], cfg["motion_min_area"])
        if cfg["enable_ultrasonic"]:
            ultrasonic = _try_init("Ultrasonic", lambda: Ultrasonic(
                cfg["ultrasonic_trig_pin"], cfg["ultrasonic_echo_pin"]))
        if cfg["enable_weight"]:
            weight = _try_init("Weight", lambda: Weight(
                cfg["weight_dout_pin"], cfg["weight_sck_pin"], cfg["weight_samples"]))

        log.info("-------------------- Ready --------------------")
        run_pipeline(cfg, stop, triggers, ir_process, camera, ultrasonic, weight, spool, uploader)
    finally:
        stop.set()
        uploader.wake()
        for device in (camera, ultrasonic, weight):
            if device is not None:
                device.close()
        if ir_process is not None:
            ir_process.join(timeout=2)
            if ir_process.is_alive():
                ir_process.terminate()
        uploader.join(timeout=5)

if __name__ == "__main__":
    main()
