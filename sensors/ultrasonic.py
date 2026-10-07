import logging
import statistics
import threading
import time

import pigpio

log = logging.getLogger("Ultrasonic")

SPEED_OF_SOUND_CM_PER_US = 0.0343
PING_INTERVAL_S = 0.06  # HC-SR04 needs ~60 ms between pings so old echoes don't overlap


class Ultrasonic:
    def __init__(self, trig_pin, echo_pin):
        self.trig_pin = trig_pin
        self.echo_pin = echo_pin

        self.pi = pigpio.pi()
        if not self.pi.connected:
            raise RuntimeError("Cannot connect to pigpio daemon (sudo systemctl enable --now pigpiod)")

        self.pi.set_mode(trig_pin, pigpio.OUTPUT)
        self.pi.set_mode(echo_pin, pigpio.INPUT)
        self.pi.write(trig_pin, 0)

        self._rise_tick = None
        self._pulse_us = None
        self._echo_done = threading.Event()
        # pigpiod timestamps each edge in microsecond hardware ticks, so the
        # measurement doesn't depend on Python scheduling or busy-waiting.
        self._callback = self.pi.callback(echo_pin, pigpio.EITHER_EDGE, self._on_edge)

    def _on_edge(self, gpio, level, tick):
        if level == 1:
            self._rise_tick = tick
        elif level == 0 and self._rise_tick is not None:
            self._pulse_us = pigpio.tickDiff(self._rise_tick, tick)
            self._echo_done.set()

    def read_cm(self, timeout=0.1):
        """Single ping. Returns distance in cm, or None if no echo arrived."""
        self._rise_tick = None
        self._echo_done.clear()
        self.pi.gpio_trigger(self.trig_pin, 10, 1)
        if not self._echo_done.wait(timeout):
            return None
        return self._pulse_us * SPEED_OF_SOUND_CM_PER_US / 2

    def measure(self, samples=5):
        """Median of several pings. Returns None if every ping failed."""
        readings = []
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
        self.pi.stop()
