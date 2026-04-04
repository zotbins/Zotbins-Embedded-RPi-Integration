#!/usr/bin/env python3
import argparse
import json
import time

from ..weight_sensor import WeightSensor, default_calibration_path
from ..weight_sensor.errors import CalibrationError, HX711NotReadyError, HX711ReadError


def parse_args():
    p = argparse.ArgumentParser(description="Read HX711 weight once or continuously")
    p.add_argument("--dt", type=int, default=5, help="BCM GPIO for HX711 DT/DOUT")
    p.add_argument("--sck", type=int, default=6, help="BCM GPIO for HX711 SCK")
    p.add_argument("--gain", type=int, default=128, choices=[128, 64, 32])
    p.add_argument("--samples", type=int, default=12, help="samples per reading")
    p.add_argument("--every", type=float, default=0.0, help="seconds between reads; 0=read once")
    p.add_argument("--count", type=int, default=1, help="number of reads when --every > 0; 0=forever")
    p.add_argument("--raw", action="store_true", help="print raw average instead of grams")
    p.add_argument("--bin-id", type=str, default="zotbin-1")
    p.add_argument("--calibration-file", type=str, default=None)
    p.add_argument("--json", action="store_true", help="emit JSON lines")
    return p.parse_args()


def emit(obj, as_json: bool):
    if as_json:
        print(json.dumps(obj), flush=True)
    else:
        print(obj, flush=True)


def main() -> int:
    args = parse_args()
    cal_file = args.calibration_file or str(default_calibration_path(args.bin_id))
    ws = WeightSensor(dt_gpio=args.dt, sck_gpio=args.sck, gain=args.gain, calibration_file=cal_file)

    def read_once():
        ts = time.time()
        if args.raw:
            raw = ws.read_raw_avg(samples=args.samples, settle_ms=2)
            emit({"ts": ts, "raw": raw} if args.json else f"raw_avg={raw:.2f}", args.json)
        else:
            grams = ws.read_grams(samples=args.samples)
            emit({"ts": ts, "weight_grams": grams} if args.json else f"weight_grams={grams:.2f}", args.json)

    try:
        if args.every <= 0:
            read_once()
            return 0

        i = 0
        while True:
            read_once()
            i += 1
            if args.count > 0 and i >= args.count:
                break
            time.sleep(args.every)
        return 0

    except CalibrationError as e:
        emit({"error": f"CalibrationError: {e}"} if args.json else f"CalibrationError: {e}", args.json)
        return 2
    except HX711NotReadyError as e:
        emit({"error": f"HX711NotReadyError: {e}"} if args.json else f"HX711NotReadyError: {e}", args.json)
        return 3
    except HX711ReadError as e:
        emit({"error": f"HX711ReadError: {e}"} if args.json else f"HX711ReadError: {e}", args.json)
        return 4
    finally:
        ws.close()


if __name__ == "__main__":
    raise SystemExit(main())
