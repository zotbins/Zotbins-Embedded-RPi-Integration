import logging
import queue
import signal
import time

import RPi.GPIO as GPIO

log = logging.getLogger("IR")


def ir_sensor_process(output_queue, stop_event, gpio_pin=17, debounce_time=3):
    # The parent handles Ctrl+C and tells us to stop through stop_event.
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, lambda *_: stop_event.set())

    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(gpio_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    log.info("Started on GPIO %d", gpio_pin)

    trigger_count = 0
    last_trigger_time = -debounce_time

    try:
        while not stop_event.is_set():
            # Sleep in the kernel until the beam breaks (falling edge) instead of polling.
            # The timeout only exists so we notice stop_event.
            if GPIO.wait_for_edge(gpio_pin, GPIO.FALLING, timeout=500) is None:
                continue

            now = time.monotonic()
            if now - last_trigger_time < debounce_time:
                continue

            trigger_count += 1
            last_trigger_time = now
            try:
                output_queue.put_nowait({"trigger": trigger_count, "ts": now})
                log.info("Trigger #%d", trigger_count)
            except queue.Full:
                log.warning("Trigger #%d dropped, pipeline is busy", trigger_count)
    finally:
        # Only release our own pin; GPIO.cleanup() with no args would reset every pin.
        GPIO.cleanup(gpio_pin)
