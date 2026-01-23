import time

from .errors import HX711NotReadyError


class _PigpioBackend:
    def __init__(self):
        import pigpio  # type: ignore

        self.pi = pigpio.pi()
        if not self.pi.connected:
            raise RuntimeError("pigpio not connected. Start with: sudo pigpiod")

    def set_input(self, pin: int):
        self.pi.set_mode(pin, 0)  # INPUT

    def set_output(self, pin: int):
        self.pi.set_mode(pin, 1)  # OUTPUT

    def write(self, pin: int, val: int):
        self.pi.write(pin, 1 if val else 0)

    def read(self, pin: int) -> int:
        return int(self.pi.read(pin))

    def sleep_us(self, us: int):
        time.sleep(us / 1_000_000)

    def close(self):
        try:
            self.pi.stop()
        except Exception:
            pass


class _RpiGpioBackend:
    def __init__(self):
        import RPi.GPIO as GPIO  # type: ignore

        self.GPIO = GPIO
        self.GPIO.setwarnings(False)
        self.GPIO.setmode(self.GPIO.BCM)

    def set_input(self, pin: int):
        self.GPIO.setup(pin, self.GPIO.IN)

    def set_output(self, pin: int):
        self.GPIO.setup(pin, self.GPIO.OUT)

    def write(self, pin: int, val: int):
        self.GPIO.output(pin, self.GPIO.HIGH if val else self.GPIO.LOW)

    def read(self, pin: int) -> int:
        return int(self.GPIO.input(pin))

    def sleep_us(self, us: int):
        time.sleep(us / 1_000_000)

    def close(self):
        try:
            self.GPIO.cleanup()
        except Exception:
            pass


class HX711:
    """
    HX711 24-bit ADC for load cells.

    Uses pigpio if available (more stable timing). Falls back to RPi.GPIO.
    """

    GAIN_PULSES = {128: 1, 64: 3, 32: 2}

    def __init__(
        self,
        dt_gpio: int,
        sck_gpio: int,
        gain: int = 128,
        use_pigpio: bool = True,
        clock_us: int = 1,
        ready_timeout_s: float = 1.0,
    ):
        if gain not in self.GAIN_PULSES:
            raise ValueError("gain must be one of: 128, 64, 32")

        self.dt = int(dt_gpio)
        self.sck = int(sck_gpio)
        self.gain = int(gain)
        self.clock_us = int(clock_us)
        self.ready_timeout_s = float(ready_timeout_s)

        self._backend = None
        if use_pigpio:
            try:
                self._backend = _PigpioBackend()
            except Exception:
                self._backend = _RpiGpioBackend()
        else:
            self._backend = _RpiGpioBackend()

        self._backend.set_input(self.dt)
        self._backend.set_output(self.sck)
        self._backend.write(self.sck, 0)

        self._set_gain()  # prime gain

    def close(self):
        if self._backend:
            self._backend.close()
            self._backend = None

    def is_ready(self) -> bool:
        return self._backend.read(self.dt) == 0

    def _wait_ready(self):
        start = time.time()
        while not self.is_ready():
            if time.time() - start > self.ready_timeout_s:
                raise HX711NotReadyError("HX711 not ready (DOUT stayed high)")
            time.sleep(0.001)

    def power_down(self):
        self._backend.write(self.sck, 0)
        self._backend.sleep_us(self.clock_us)
        self._backend.write(self.sck, 1)
        time.sleep(0.0001)  # >60us

    def power_up(self):
        self._backend.write(self.sck, 0)
        time.sleep(0.0001)

    def _set_gain(self):
        # Gain/channel selection happens by extra pulses after 24-bit read.
        # Do one dummy read cycle to ensure the chip is in a known state.
        if self.is_ready():
            self.read_raw()

    @staticmethod
    def _twos_complement_24(val: int) -> int:
        val &= 0xFFFFFF
        if val & 0x800000:
            val -= 1 << 24
        return val

    def read_raw(self) -> int:
        self._wait_ready()

        data = 0
        for _ in range(24):
            self._backend.write(self.sck, 1)
            self._backend.sleep_us(self.clock_us)
            data = (data << 1) | self._backend.read(self.dt)
            self._backend.write(self.sck, 0)
            self._backend.sleep_us(self.clock_us)

        for _ in range(self.GAIN_PULSES[self.gain]):
            self._backend.write(self.sck, 1)
            self._backend.sleep_us(self.clock_us)
            self._backend.write(self.sck, 0)
            self._backend.sleep_us(self.clock_us)

        return self._twos_complement_24(data)