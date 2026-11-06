import logging
import statistics
import threading
import time

import lgpio

log = logging.getLogger("Ultrasonic")

SPEED_OF_SOUND_CM_PER_US = 0.0343
PING_INTERVAL_S = 0.06  # HC-SR04 needs ~60 ms between pings so old echoes don't overlap
GPIO_CHIP = 0  # The 40-pin header on a Pi 3 / 4 (and a Pi 5 on current kernels)


class Ultrasonic:
    def __init__(self, trig_pin, echo_pin):
        self.trig_pin = trig_pin
        self.echo_pin = echo_pin

        self.chip = lgpio.gpiochip_open(GPIO_CHIP)
        try:
            lgpio.gpio_claim_output(self.chip, trig_pin, 0)
            lgpio.gpio_claim_alert(self.chip, echo_pin, lgpio.BOTH_EDGES)
        except lgpio.error:
            lgpio.gpiochip_close(self.chip)
            raise

        self._rise_ns = None
        self._pulse_us = None
        self._echo_done = threading.Event()
        self._lock = threading.Lock()  # the pipeline and the fullness monitor thread both measure
        # The kernel timestamps each edge in nanoseconds, so the
        # measurement doesn't depend on Python scheduling or busy-waiting.
        self._callback = lgpio.callback(self.chip, echo_pin, lgpio.BOTH_EDGES, self._on_edge)

    def _on_edge(self, chip, gpio, level, timestamp_ns):
        if level == 1:
            self._rise_ns = timestamp_ns
        elif level == 0 and self._rise_ns is not None:
            self._pulse_us = (timestamp_ns - self._rise_ns) / 1000
            self._echo_done.set()

    def read_cm(self, timeout=0.1):
        """Single ping. Returns distance in cm, or None if no echo arrived."""
        self._rise_ns = None
        self._echo_done.clear()
        lgpio.tx_pulse(self.chip, self.trig_pin, 10, 10, 0, 1)  # one 10 us trigger pulse
        if not self._echo_done.wait(timeout):
            return None
        return self._pulse_us * SPEED_OF_SOUND_CM_PER_US / 2

    def measure(self, samples=5):
        """Median of several pings. Returns None if every ping failed."""
        readings = []
        with self._lock:
            for i in range(samples):
                if i:
                    time.sleep(PING_INTERVAL_S)
                cm = self.read_cm()
                if cm is not None:
                    readings.append(cm)

        if not readings:
            log.warning("No echo received in %d pings", samples)
            return None
        return statistics.median(readings)

    def close(self):
        self._callback.cancel()
        lgpio.gpiochip_close(self.chip)  # also releases both pins


if __name__ == "__main__":
    # Standalone test: python -m sensors.ultrasonic [--trig N] [--echo N] [--samples N] [--interval S]
    import argparse

    from config import CONFIG

    parser = argparse.ArgumentParser(description="Print the measured distance repeatedly.")
    parser.add_argument("--trig", type=int, default=CONFIG["ultrasonic_trig_pin"])
    parser.add_argument("--echo", type=int, default=CONFIG["ultrasonic_echo_pin"])
    parser.add_argument("--samples", type=int, default=CONFIG["ultrasonic_samples"])
    parser.add_argument("--interval", type=float, default=0.5, help="seconds between readings")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s", datefmt="%H:%M:%S")

    sensor = Ultrasonic(args.trig, args.echo)
    print(f"TRIG={args.trig} ECHO={args.echo}, median of {args.samples} pings. Ctrl+C to quit.")
    try:
        while True:
            cm = sensor.measure(args.samples)
            print("no echo" if cm is None else f"{cm:6.1f} cm")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        sensor.close()
