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


if __name__ == "__main__":
    # Standalone test: python -m sensors.ir_sensor [--pin N] [--debounce S] [--state [--interval S]]
    import argparse
    import multiprocessing as mp

    from config import CONFIG

    parser = argparse.ArgumentParser(description="Print a line every time the IR beam breaks.")
    parser.add_argument("--pin", type=int, default=CONFIG["ir_gpio_pin"])
    parser.add_argument("--debounce", type=float, default=CONFIG["debounce_time"])
    parser.add_argument("--state", action="store_true", help="continuously print the beam state instead of triggers")
    parser.add_argument("--interval", type=float, default=0.2, help="seconds between --state prints")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s", datefmt="%H:%M:%S")

    if args.state:
        # Raw view for wiring/alignment: same pin setup as the sensor process, no edge detection.
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(args.pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        print(f"GPIO {args.pin} state every {args.interval}s. Ctrl+C to quit.")
        try:
            while True:
                level = GPIO.input(args.pin)
                print(f"{time.strftime('%H:%M:%S')}  GPIO{args.pin}={level}  {'clear' if level else 'BROKEN'}", flush=True)
                time.sleep(args.interval)
        except KeyboardInterrupt:
            pass
        finally:
            GPIO.cleanup(args.pin)
        raise SystemExit

    # Run the real sensor process exactly as main.py does, and print what it sends.
    triggers, stop = mp.Queue(), mp.Event()
    proc = mp.Process(target=ir_sensor_process, args=(triggers, stop, args.pin, args.debounce), daemon=True)
    proc.start()
    print(f"Watching GPIO {args.pin} (debounce {args.debounce}s). Break the beam; Ctrl+C to quit.")
    try:
        while proc.is_alive():
            try:
                trigger = triggers.get(timeout=0.5)
            except queue.Empty:
                continue
            print(f"Beam broken: trigger #{trigger['trigger']}")
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        proc.join(timeout=2)
