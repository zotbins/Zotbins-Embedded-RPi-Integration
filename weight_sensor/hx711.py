import time
from dataclasses import dataclass

import RPi.GPIO as GPIO

from .errors import HX711NotReadyError, HX711ReadError


def _busy_wait_us(us: float):
    end = time.perf_counter_ns() + int(us * 1000)
    while time.perf_counter_ns() < end:
        pass


@dataclass(frozen=True)
class HX711Config:
    dt_gpio: int
    sck_gpio: int
    gain: int = 128
    ready_timeout_s: float = 0.8
    clock_delay_us: float = 2.0
    max_read_duration_us: float = 5000.0


class HX711:
    _GAIN_PULSES = {128: 1, 64: 3, 32: 2}

    def __init__(self, config: HX711Config):
        if config.gain not in self._GAIN_PULSES:
            raise ValueError("gain must be 128, 64, or 32")
        self.cfg = config

        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.cfg.dt_gpio, GPIO.IN)
        GPIO.setup(self.cfg.sck_gpio, GPIO.OUT, initial=GPIO.LOW)

        self._ensure_awake()
        self._prime_gain()

    def close(self):
        try:
            GPIO.cleanup([self.cfg.dt_gpio, self.cfg.sck_gpio])
        except Exception:
            pass

    def _ensure_awake(self):
        GPIO.output(self.cfg.sck_gpio, GPIO.LOW)
        time.sleep(0.001)

    def _prime_gain(self):
        try:
            self.read_raw()
        except Exception:
            pass

    def is_ready(self) -> bool:
        return GPIO.input(self.cfg.dt_gpio) == 0

    def _wait_ready(self):
        start = time.monotonic()
        while not self.is_ready():
            if time.monotonic() - start >= self.cfg.ready_timeout_s:
                raise HX711NotReadyError("HX711 not ready (DOUT stayed high)")
            time.sleep(0.001)

    @staticmethod
    def _twos_comp_24(x: int) -> int:
        x &= 0xFFFFFF
        if x & 0x800000:
            x -= 1 << 24
        return x

    def _pulse(self) -> int:
        GPIO.output(self.cfg.sck_gpio, GPIO.HIGH)
        _busy_wait_us(self.cfg.clock_delay_us)
        bit = GPIO.input(self.cfg.dt_gpio)
        GPIO.output(self.cfg.sck_gpio, GPIO.LOW)
        _busy_wait_us(self.cfg.clock_delay_us)
        return bit

    def read_raw(self) -> int:
        self._wait_ready()

        t0 = time.perf_counter_ns()

        value = 0
        for _ in range(24):
            value = (value << 1) | self._pulse()

        for _ in range(self._GAIN_PULSES[self.cfg.gain]):
            GPIO.output(self.cfg.sck_gpio, GPIO.HIGH)
            _busy_wait_us(self.cfg.clock_delay_us)
            GPIO.output(self.cfg.sck_gpio, GPIO.LOW)
            _busy_wait_us(self.cfg.clock_delay_us)

        elapsed_us = (time.perf_counter_ns() - t0) / 1000.0
        if elapsed_us > self.cfg.max_read_duration_us:
            raise HX711ReadError(
                f"Read took {elapsed_us:.0f} us (limit {self.cfg.max_read_duration_us:.0f} us)"
            )

        raw = self._twos_comp_24(value)

        if raw == -1:
            raise HX711ReadError("Invalid raw (0xFFFFFF)")
        if raw == 0x7FFFFF:
            raise HX711ReadError("Invalid raw (0x7FFFFF)")
        if raw == -0x800000:
            raise HX711ReadError("Invalid raw (-0x800000)")

        return raw