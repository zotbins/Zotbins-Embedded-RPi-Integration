import json
import time
from pathlib import Path
from statistics import mean

from .errors import CalibrationError
from .hx711 import HX711

CAL_FILE = Path(__file__).with_name("calibration.json")


class WeightSensor:
    def __init__(
        self,
        dt_gpio: int = 5,
        sck_gpio: int = 6,
        gain: int = 128,
        use_pigpio: bool = True,
    ):
        self.hx = HX711(dt_gpio=dt_gpio, sck_gpio=sck_gpio, gain=gain, use_pigpio=use_pigpio)
        self.offset = 0.0
        self.scale = 1.0  # raw units per gram
        self.load_calibration()

    def close(self):
        self.hx.close()

    def load_calibration(self):
        if not CAL_FILE.exists():
            return
        try:
            data = json.loads(CAL_FILE.read_text())
            self.offset = float(data["offset"])
            self.scale = float(data["scale"])
            if self.scale == 0:
                raise ValueError("scale cannot be 0")
        except Exception as e:
            raise CalibrationError(f"Bad calibration file: {e}")

    def save_calibration(self):
        payload = {"offset": float(self.offset), "scale": float(self.scale), "updated_at": int(time.time())}
        CAL_FILE.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    def _trimmed_mean(self, values, trim_each_side: int = 1) -> float:
        values = list(values)
        values.sort()
        if len(values) >= (trim_each_side * 2 + 3):
            values = values[trim_each_side:-trim_each_side]
        return float(mean(values))

    def read_raw_avg(self, samples: int = 10, settle_ms: int = 0) -> float:
        vals = []
        for _ in range(samples):
            vals.append(self.hx.read_raw())
            if settle_ms:
                time.sleep(settle_ms / 1000.0)
        return self._trimmed_mean(vals, trim_each_side=1)

    def tare(self, samples: int = 20):
        self.offset = self.read_raw_avg(samples=samples, settle_ms=5)
        self.save_calibration()

    def calibrate_with_known_weight(self, known_grams: float, samples: int = 30):
        if known_grams <= 0:
            raise ValueError("known_grams must be > 0")
        raw = self.read_raw_avg(samples=samples, settle_ms=5)
        delta = raw - self.offset
        if abs(delta) < 1000:
            raise CalibrationError("Signal too small. Check wiring or increase known weight.")
        self.scale = delta / float(known_grams)
        self.save_calibration()

    def read_grams(self, samples: int = 10) -> float:
        if self.scale == 0:
            raise CalibrationError("scale is 0 (calibration missing?)")
        raw = self.read_raw_avg(samples=samples, settle_ms=2)
        return (raw - self.offset) / self.scale