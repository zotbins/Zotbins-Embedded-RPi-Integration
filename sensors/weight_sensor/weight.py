import json
import os
import time
import warnings
from dataclasses import dataclass
from pathlib import Path
from statistics import median

from .errors import CalibrationError, HX711NotReadyError, HX711ReadError
from .hx711 import HX711, HX711Config


def _default_config_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg)
    return Path.home() / ".config"


def default_calibration_path(bin_id: str) -> Path:
    safe = "".join(
        ch if ch.isalnum() or ch in ("-", "_") else "_"
        for ch in (bin_id or "default")
    )
    return _default_config_dir() / "weight_sensor" / f"{safe}.json"


@dataclass
class Calibration:
    offset: float = 0.0
    scale: float = 0.0
    updated_at: int = 0


class WeightSensor:
    def __init__(
        self,
        dt_gpio: int = 5,
        sck_gpio: int = 6,
        gain: int = 128,
        use_pigpio: bool = False,
        calibration_file: str | Path | None = None,
    ):
        if use_pigpio:
            warnings.warn(
                "pigpio backend is not implemented; falling back to RPi.GPIO with busy-wait timing.",
                stacklevel=2,
            )

        self.hx = HX711(
            HX711Config(dt_gpio=dt_gpio, sck_gpio=sck_gpio, gain=gain)
        )
        self.cal = Calibration()
        self._cal_file = (
            Path(calibration_file)
            if calibration_file is not None
            else Path(__file__).with_name("default")
        )
        self._load_calibration()

    @property
    def offset(self) -> float:
        return float(self.cal.offset)

    @property
    def scale(self) -> float:
        return float(self.cal.scale)

    @property
    def calibration_file(self) -> Path:
        return self._cal_file

    def close(self):
        self.hx.close()

    def _load_calibration(self):
        if not self._cal_file.exists():
            return
        try:
            data = json.loads(self._cal_file.read_text())
            self.cal.offset = float(data.get("offset", 0.0))
            self.cal.scale = float(data.get("scale", 0.0))
            self.cal.updated_at = int(data.get("updated_at", 0))
        except Exception:
            return

    def _save_calibration(self):
        self.cal.updated_at = int(time.time())
        self._cal_file.parent.mkdir(parents=True, exist_ok=True)
        self._cal_file.write_text(
            json.dumps(
                {
                    "offset": float(self.cal.offset),
                    "scale": float(self.cal.scale),
                    "updated_at": int(self.cal.updated_at),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )

    @staticmethod
    def _robust_mean(values: list[float]) -> float:
        if len(values) < 4:
            return float(median(values))

        s = sorted(values)
        n = len(s)
        q1 = s[n // 4]
        q3 = s[(3 * n) // 4]
        iqr = q3 - q1

        if iqr == 0:
            return float(median(s))

        margin = 1.5 * iqr
        lo = q1 - margin
        hi = q3 + margin
        filtered = [v for v in s if lo <= v <= hi]

        if len(filtered) < 3:
            return float(median(s))

        return sum(filtered) / len(filtered)

    def read_raw_samples(
        self, target: int, max_attempts: int, settle_ms: int = 0
    ) -> list[int]:
        vals: list[int] = []
        attempts = 0
        while len(vals) < target and attempts < max_attempts:
            attempts += 1
            try:
                r = self.hx.read_raw()
                vals.append(r)
            except (HX711NotReadyError, HX711ReadError):
                pass
            if settle_ms:
                time.sleep(settle_ms / 1000.0)
        if len(vals) < target:
            raise HX711NotReadyError(
                f"Insufficient valid samples ({len(vals)}/{target} in {attempts} attempts)"
            )
        return vals

    def read_raw_avg(self, samples: int = 10, settle_ms: int = 2) -> float:
        vals = self.read_raw_samples(
            target=samples,
            max_attempts=max(samples * 6, 30),
            settle_ms=settle_ms,
        )
        return self._robust_mean([float(v) for v in vals])

    def tare(self, samples: int = 25):
        off = self.read_raw_avg(samples=samples, settle_ms=5)
        self.cal.offset = float(off)
        self._save_calibration()

    def calibrate_with_known_weight(
        self,
        known_grams: float,
        samples: int = 40,
        min_delta_raw: float = 5000.0,
    ):
        if not (known_grams > 0):
            raise ValueError("known_grams must be > 0")

        loaded = self.read_raw_avg(samples=samples, settle_ms=5)
        delta = loaded - float(self.cal.offset)

        if abs(delta) < float(min_delta_raw):
            raise CalibrationError(
                "Signal too small. Check mechanics/wiring or use heavier weight."
            )

        scale = delta / float(known_grams)
        if not (abs(scale) > 0):
            raise CalibrationError("Invalid scale computed")

        self.cal.scale = float(scale)
        self._save_calibration()

    def read_grams(self, samples: int = 12) -> float:
        if self.cal.scale == 0:
            raise CalibrationError("Missing calibration (scale=0)")

        raw = self.read_raw_avg(samples=samples, settle_ms=2)
        return (raw - float(self.cal.offset)) / float(self.cal.scale)